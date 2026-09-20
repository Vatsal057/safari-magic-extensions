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

    // MARK: - Archive safety

    /// Reject archive members that could write outside the extraction directory.
    ///
    /// Mirrors `assert_archive_is_safe` in `safari-magic-ext.py`. Packages come
    /// from the internet, so absolute paths and `..` traversal are refused
    /// before a single byte is extracted.
    private func validateArchiveEntries(at archiveURL: URL) throws {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/unzip")
        process.arguments = ["-Z1", archiveURL.path]
        let outPipe = Pipe()
        process.standardOutput = outPipe
        process.standardError = Pipe()
        try process.run()
        let listingData = outPipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()

        guard process.terminationStatus == 0,
              let listing = String(data: listingData, encoding: .utf8) else {
            throw NSError(domain: "PackageManager", code: 422, userInfo: [
                NSLocalizedDescriptionKey: "Could not read the contents of \(archiveURL.lastPathComponent). It may not be a valid .magicext archive."
            ])
        }

        for rawEntry in listing.split(separator: "\n") {
            let entry = rawEntry.trimmingCharacters(in: .whitespacesAndNewlines)
            if entry.isEmpty { continue }

            let normalized = entry.replacingOccurrences(of: "\\", with: "/")
            let isAbsolute = normalized.hasPrefix("/")
            let hasDriveLetter = normalized.count > 1
                && normalized[normalized.index(normalized.startIndex, offsetBy: 1)] == ":"
            let traverses = normalized.split(separator: "/").contains("..")

            if isAbsolute || hasDriveLetter || traverses {
                throw NSError(domain: "PackageManager", code: 403, userInfo: [
                    NSLocalizedDescriptionKey: "Refusing to install: archive member '\(entry)' tries to escape its folder."
                ])
            }
        }
    }

    /// Reject symlinks in a freshly extracted package.
    ///
    /// A symlink is inert inside the temp directory, but copying it into
    /// Safari's container would let the package point at arbitrary files.
    private func assertNoSymlinks(in directory: URL) throws {
        let keys: [URLResourceKey] = [.isSymbolicLinkKey]
        guard let walker = FileManager.default.enumerator(
            at: directory,
            includingPropertiesForKeys: keys,
            options: []
        ) else { return }

        for case let fileURL as URL in walker {
            let values = try? fileURL.resourceValues(forKeys: Set(keys))
            if values?.isSymbolicLink == true {
                throw NSError(domain: "PackageManager", code: 403, userInfo: [
                    NSLocalizedDescriptionKey: "Refusing to install: package contains a symbolic link (\(fileURL.lastPathComponent))."
                ])
            }
        }
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

    public func packFolder(
        sourceFolder: URL,
        destinationDir: URL,
        author: String? = nil,
        customName: String? = nil,
        customPrompt: String? = nil,
        customSymbol: String? = nil,
        customColor: String? = nil
    ) throws -> URL {
        guard FileManager.default.fileExists(atPath: sourceFolder.path) else {
            throw NSError(domain: "PackageManager", code: 404, userInfo: [
                NSLocalizedDescriptionKey: "Source folder not found on disk at \(sourceFolder.path)"
            ])
        }

        // Prepare temporary staging directory
        let tempDir = FileManager.default.temporaryDirectory.appendingPathComponent("pack_stage_\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDir) }

        // Copy source files to staging
        let contents = try FileManager.default.contentsOfDirectory(at: sourceFolder, includingPropertiesForKeys: nil)
        for item in contents {
            if item.lastPathComponent.hasPrefix(".") || item.lastPathComponent == "node_modules" { continue }
            let dest = tempDir.appendingPathComponent(item.lastPathComponent)
            try FileManager.default.copyItem(at: item, to: dest)
        }

        // Check or synthesize manifest.json
        let manifestFile = tempDir.appendingPathComponent("manifest.json")
        var name = customName ?? sourceFolder.lastPathComponent
        var desc = "\(name) Extension"
        var prompt = customPrompt ?? "Create \(name)"
        var symbol = customSymbol ?? "puzzlepiece.extension"
        let color = customColor ?? "blue"

        if FileManager.default.fileExists(atPath: manifestFile.path),
           let data = try? Data(contentsOf: manifestFile),
           var json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] {
            if let n = json["name"] as? String, !n.isEmpty { name = customName ?? n }
            if let d = json["description"] as? String, !d.isEmpty { desc = d }

            var specific = json["browser_specific_settings"] as? [String: Any] ?? [:]
            var safari = specific["safari"] as? [String: Any] ?? [:]
            if let p = safari["prompt"] as? String, !p.isEmpty {
                prompt = customPrompt ?? p
            } else {
                safari["prompt"] = prompt
                specific["safari"] = safari
                json["browser_specific_settings"] = specific
            }

            if let icons = json["icon_variants"] as? [[String: Any]],
               let first = icons.first,
               let anyVal = first["any"] as? String,
               anyVal.hasPrefix("symbol:") {
                symbol = customSymbol ?? anyVal.replacingOccurrences(of: "symbol:", with: "")
            } else {
                json["icon_variants"] = [["any": "symbol:\(symbol)"]]
            }

            if let updatedData = try? JSONSerialization.data(withJSONObject: json, options: .prettyPrinted) {
                try? updatedData.write(to: manifestFile)
            }
        } else {
            // Synthesize manifest.json if missing
            let htmlFiles = contents.filter { $0.pathExtension.lowercased() == "html" }
            let entry = htmlFiles.first(where: { $0.lastPathComponent == "index.html" })?.lastPathComponent
                ?? htmlFiles.first?.lastPathComponent ?? "newtab.html"

            let synthManifest: [String: Any] = [
                "manifest_version": 3,
                "name": name,
                "version": "1.0",
                "description": desc,
                "browser_url_overrides": ["newtab": entry],
                "browser_specific_settings": [
                    "safari": ["prompt": prompt]
                ],
                "icon_variants": [["any": "symbol:\(symbol)"]]
            ]
            if let synthData = try? JSONSerialization.data(withJSONObject: synthManifest, options: .prettyPrinted) {
                try? synthData.write(to: manifestFile)
            }
        }

        // Write magic.json
        let meta = MagicPackageMeta(
            magic_format_version: 1,
            id: UUID().uuidString.uppercased(),
            name: name,
            author: author ?? NSUserName(),
            version: "1.0",
            description: desc,
            prompt: prompt,
            selected_symbol: symbol,
            symbol_color_name: color,
            packaged_at: ISO8601DateFormatter().string(from: Date())
        )
        let metaData = try JSONEncoder().encode(meta)
        try metaData.write(to: tempDir.appendingPathComponent("magic.json"))

        let safeName = name.components(separatedBy: CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "_-")).inverted).joined(separator: "_")
        let outputURL = destinationDir.appendingPathComponent("\(safeName).magicext")

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
        // Screen the archive before extracting anything.
        try validateArchiveEntries(at: sourceURL)

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

        // Nothing symlinked may be copied into Safari's container.
        try assertNoSymlinks(in: tempDir)

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

    public func installFromDirectory(sourceURL: URL, relaunchSafari: Bool = true) throws -> String {
        let isAlreadyInside = sourceURL.deletingLastPathComponent().resolvingSymlinksInPath().path == ExtensionDatabase.magicExtensionsDir.resolvingSymlinksInPath().path

        var targetFolderURL = sourceURL
        var destFolderName = sourceURL.lastPathComponent

        if !isAlreadyInside {
            destFolderName = cleanTargetFolderName(for: sourceURL.lastPathComponent)
            targetFolderURL = ExtensionDatabase.magicExtensionsDir.appendingPathComponent(destFolderName)
            if FileManager.default.fileExists(atPath: targetFolderURL.path) {
                try? FileManager.default.removeItem(at: targetFolderURL)
            }
            let copyProcess = Process()
            copyProcess.executableURL = URL(fileURLWithPath: "/usr/bin/ditto")
            copyProcess.arguments = [sourceURL.path, targetFolderURL.path]
            try copyProcess.run()
            copyProcess.waitUntilExit()
        }

        var extName = destFolderName
        var extPrompt = ""
        var extDesc = ""
        var extSymbol = "puzzlepiece.extension"
        let extColor = "blue"

        let manifestURL = targetFolderURL.appendingPathComponent("manifest.json")
        if FileManager.default.fileExists(atPath: manifestURL.path),
           let data = try? Data(contentsOf: manifestURL),
           let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] {
            if let n = json["name"] as? String, !n.isEmpty { extName = n }
            if let d = json["description"] as? String { extDesc = d }
            if let specific = json["browser_specific_settings"] as? [String: Any],
               let safari = specific["safari"] as? [String: Any],
               let p = safari["prompt"] as? String {
                extPrompt = p
            }
            if let icons = json["icon_variants"] as? [[String: Any]],
               let first = icons.first,
               let anyVal = first["any"] as? String,
               anyVal.hasPrefix("symbol:") {
                extSymbol = anyVal.replacingOccurrences(of: "symbol:", with: "")
            }
        }

        if extPrompt.isEmpty { extPrompt = extDesc.isEmpty ? extName : extDesc }

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
