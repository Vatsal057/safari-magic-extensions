import Foundation

public final class CommunityRegistryClient: ObservableObject {
    public static let shared = CommunityRegistryClient()

    @Published public var extensions: [CommunityExtension] = []
    @Published public var isLoading: Bool = false
    @Published public var errorMessage: String? = nil

    private let remoteURL = URL(string: "https://vatsal057.github.io/safari-magic-extensions/community_registry.json")!

    private init() {}

    @MainActor
    public func fetchCatalog() async {
        isLoading = true
        errorMessage = nil
        do {
            let (data, response) = try await URLSession.shared.data(from: remoteURL)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                throw NSError(domain: "CommunityRegistry", code: 400, userInfo: [NSLocalizedDescriptionKey: "Bad response from catalog"])
            }
            let payload = try JSONDecoder().decode(CommunityRegistryPayload.self, from: data)
            self.extensions = payload.extensions
        } catch {
            // Try loading local fallback from repo if running locally
            if let localURL = Bundle.main.url(forResource: "community_registry", withExtension: "json"),
               let localData = try? Data(contentsOf: localURL),
               let payload = try? JSONDecoder().decode(CommunityRegistryPayload.self, from: localData) {
                self.extensions = payload.extensions
            } else {
                self.errorMessage = "Could not fetch catalog: \(error.localizedDescription)"
            }
        }
        isLoading = false
    }

    public func downloadAndInstall(extension item: CommunityExtension) async throws -> String {
        guard let downloadStr = item.download_url else {
            throw NSError(domain: "CommunityRegistry", code: 404, userInfo: [NSLocalizedDescriptionKey: "No download URL available"])
        }

        // 1. Check local file paths first (for fast local execution)
        let filename = URL(string: downloadStr)?.lastPathComponent ?? downloadStr
        let localCandidates = [
            URL(fileURLWithPath: downloadStr),
            URL(fileURLWithPath: FileManager.default.currentDirectoryPath).appendingPathComponent(downloadStr),
            URL(fileURLWithPath: FileManager.default.currentDirectoryPath).appendingPathComponent("packages").appendingPathComponent(filename),
            Bundle.main.bundleURL.deletingLastPathComponent().appendingPathComponent("packages").appendingPathComponent(filename),
            FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Desktop/MagikExtension/packages").appendingPathComponent(filename)
        ]
        for candidate in localCandidates {
            if FileManager.default.fileExists(atPath: candidate.path) {
                return try PackageManager.shared.installPackage(from: candidate, relaunchSafari: true)
            }
        }

        // 2. Resolve remote URL
        var targetURL: URL
        if downloadStr.hasPrefix("http://") || downloadStr.hasPrefix("https://") {
            guard let u = URL(string: downloadStr) else { throw NSError(domain: "CommunityRegistry", code: 400, userInfo: [NSLocalizedDescriptionKey: "Invalid URL"]) }
            targetURL = u
        } else {
            // Relative URL on GitHub Pages
            targetURL = URL(string: "https://vatsal057.github.io/safari-magic-extensions/\(downloadStr)")!
        }

        let (tempDownloadedURL, response) = try await URLSession.shared.download(from: targetURL)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            let status = (response as? HTTPURLResponse)?.statusCode ?? -1
            throw NSError(domain: "CommunityRegistry", code: status, userInfo: [
                NSLocalizedDescriptionKey: "Download failed with HTTP \(status) from \(targetURL.lastPathComponent)"
            ])
        }

        let packageURL = FileManager.default.temporaryDirectory.appendingPathComponent("\(item.id).magicext")
        if FileManager.default.fileExists(atPath: packageURL.path) {
            try? FileManager.default.removeItem(at: packageURL)
        }
        try FileManager.default.moveItem(at: tempDownloadedURL, to: packageURL)
        defer { try? FileManager.default.removeItem(at: packageURL) }

        return try PackageManager.shared.installPackage(from: packageURL, relaunchSafari: true)
    }
}
