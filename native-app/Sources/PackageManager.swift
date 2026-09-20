import Foundation
import AppKit

public final class PackageManager {
    public static let shared = PackageManager()

    private init() {}

    public func cleanTargetFolderName(for name: String) -> String {
        let cleaned = name.components(separatedBy: CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "_-")).inverted).joined()
        let base = cleaned.isEmpty ? "CustomExtension" : cleaned
        let hex = String(UUID().uuidString.prefix(4))
        return "\(base)-\(hex)"
    }

    public func pack(extension ext: InstalledExtension, destinationDir: URL, author: String? = nil) throws -> URL {
        let sourceURL = URL(fileURLWithPath: ext.folderPath)
        guard FileManager.default.fileExists(atPath: sourceURL.path) else {
            throw NSError(domain: "PackageManager", code: 404, userInfo: [
                NSLocalizedDescriptionKey: "Extension directory not found on disk at \(sourceURL.path)"
            ])
        }

        let safeName = ext.name.components(separatedBy: CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "_-")).inverted).joined(separator: "_")
        let outputURL = destinationDir.appendingPathComponent("\(safeName).magicext")

        // Prepare temporary staging directory
        let tempDir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDir) }

        // Copy source files to staging
        let contents = try FileManager.default.contentsOfDirectory(at: sourceURL, includingPropertiesForKeys: nil)
        for item in contents {
            if item.lastPathComponent.hasPrefix(".") || item.lastPathComponent == "node_modules" { continue }
            let dest = tempDir.appendingPathComponent(item.lastPathComponent)
            try FileManager.default.copyItem(at: item, to: dest)
        }

        // Write magic.json
        let meta = MagicPackageMeta(
            magic_format_version: 1,
            id: ext.id,
            name: ext.name,
            author: author ?? NSUserName(),
            version: "1.0",
            description: ext.description,
            prompt: ext.prompt,
            selected_symbol: ext.selectedSymbol,
            symbol_color_name: ext.symbolColorName,
            packaged_at: ISO8601DateFormatter().string(from: Date())
        )
        let metaData = try JSONEncoder().encode(meta)
        try metaData.write(to: tempDir.appendingPathComponent("magic.json"))

        // Compress using macOS ditto
        if FileManager.default.fileExists(atPath: outputURL.path) {
            try? FileManager.default.removeItem(at: outputURL)
        }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/ditto")
        process.arguments = ["-c", "-k", "--sequesterRsrc", tempDir.path, outputURL.path]
        try process.run()
        process.waitUntilExit()

        guard process.terminationStatus == 0 else {
            throw NSError(domain: "PackageManager", code: Int(process.terminationStatus), userInfo: [
                NSLocalizedDescriptionKey: "Failed to compress .magicext archive with ditto."
            ])
        }

        return outputURL
    }

    public func installPackage(from sourceURL: URL, relaunchSafari: Bool = true) throws -> String {
        let tempDir = FileManager.default.temporaryDirectory.appendingPathComponent("ext_extract_\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDir) }

        // Unpack archive using ditto
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/ditto")
        process.arguments = ["-x", "-k", sourceURL.path, tempDir.path]
        let errPipe = Pipe()
        process.standardError = errPipe
        try process.run()
        process.waitUntilExit()

        guard process.terminationStatus == 0 else {
            let errData = errPipe.fileHandleForReading.readDataToEndOfFile()
            let errMsg = String(data: errData, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            throw NSError(domain: "PackageManager", code: Int(process.terminationStatus), userInfo: [
                NSLocalizedDescriptionKey: "Extraction error: \(errMsg.isEmpty ? "Invalid package archive" : errMsg)"
            ])
        }

        // Read magic.json if present
        var extName: String = sourceURL.deletingPathExtension().lastPathComponent
        var extPrompt: String = ""
        var extDesc: String = ""
        var extSymbol: String = "puzzlepiece.extension"
        var extColor: String = "blue"

        let magicFile = tempDir.appendingPathComponent("magic.json")
        if FileManager.default.fileExists(atPath: magicFile.path),
           let data = try? Data(contentsOf: magicFile),
           let meta = try? JSONDecoder().decode(MagicPackageMeta.self, from: data) {
            if let n = meta.name, !n.isEmpty { extName = n }
            if let p = meta.prompt, !p.isEmpty { extPrompt = p }
            if let d = meta.description, !d.isEmpty { extDesc = d }
            if let s = meta.selected_symbol, !s.isEmpty { extSymbol = s }
            if let c = meta.symbol_color_name, !c.isEmpty { extColor = c }
            try? FileManager.default.removeItem(at: magicFile)
        }

        // If manifest.json exists, ensure prompt is injected
        let manifestFile = tempDir.appendingPathComponent("manifest.json")
        if FileManager.default.fileExists(atPath: manifestFile.path),
           let mData = try? Data(contentsOf: manifestFile),
           var mJson = (try? JSONSerialization.jsonObject(with: mData)) as? [String: Any] {
            if extName.isEmpty, let mName = mJson["name"] as? String { extName = mName }
            if extDesc.isEmpty, let mDesc = mJson["description"] as? String { extDesc = mDesc }

            var specific = mJson["browser_specific_settings"] as? [String: Any] ?? [:]
            var safari = specific["safari"] as? [String: Any] ?? [:]
            if !extPrompt.isEmpty {
                safari["prompt"] = extPrompt
            }
            specific["safari"] = safari
            mJson["browser_specific_settings"] = specific

            if let updatedData = try? JSONSerialization.data(withJSONObject: mJson, options: .prettyPrinted) {
                try? updatedData.write(to: manifestFile)
            }
        }

        // Copy to Safari storage directory
        let destFolderName = cleanTargetFolderName(for: extName)
        let destFolderURL = ExtensionDatabase.magicExtensionsDir.appendingPathComponent(destFolderName)

        let copyProcess = Process()
        copyProcess.executableURL = URL(fileURLWithPath: "/usr/bin/ditto")
        copyProcess.arguments = [tempDir.path, destFolderURL.path]
        try copyProcess.run()
        copyProcess.waitUntilExit()

        guard copyProcess.terminationStatus == 0 else {
            throw NSError(domain: "PackageManager", code: Int(copyProcess.terminationStatus), userInfo: [
                NSLocalizedDescriptionKey: "Failed to copy extension files into Safari directory."
            ])
        }

        // Register in SQLite
        let extId = try ExtensionDatabase.shared.registerExtension(
            name: extName,
            directoryName: destFolderName,
            symbol: extSymbol,
            color: extColor,
            prompt: extPrompt,
            description: extDesc
        )

        if relaunchSafari {
            Self.relaunchSafari()
        }

        return extId
    }

    public static func relaunchSafari() {
        let killProcess = Process()
        killProcess.executableURL = URL(fileURLWithPath: "/usr/bin/killall")
        killProcess.arguments = ["Safari"]
        try? killProcess.run()
        killProcess.waitUntilExit()

        Thread.sleep(forTimeInterval: 0.8)

        let openProcess = Process()
        openProcess.executableURL = URL(fileURLWithPath: "/usr/bin/open")
        openProcess.arguments = ["-a", "Safari"]
        try? openProcess.run()
    }
}
