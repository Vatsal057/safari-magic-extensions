import Foundation

/// Location of the published community catalog.
///
/// Kept in sync with `DEFAULT_REGISTRY_URL` in safari-magic-ext.py and the
/// `download_url` values that build_registry.py writes (relative to this base).
public enum RegistryEndpoint {
    public static let catalogURL = URL(
        string: "https://vatsal057.github.io/safari-magic-extensions/community_registry.json"
    )!

    /// Base used to resolve relative `download_url` values from the catalog.
    public static var baseURL: URL {
        catalogURL.deletingLastPathComponent()
    }
}

public final class CommunityRegistryClient: ObservableObject {
    public static let shared = CommunityRegistryClient()

    @Published public var extensions: [CommunityExtension] = []
    @Published public var isLoading: Bool = false
    @Published public var errorMessage: String? = nil

    private init() {}

    @MainActor
    public func fetchCatalog() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let (data, response) = try await URLSession.shared.data(from: RegistryEndpoint.catalogURL)
            guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
                let status = (response as? HTTPURLResponse)?.statusCode ?? -1
                throw NSError(domain: "CommunityRegistry", code: status, userInfo: [
                    NSLocalizedDescriptionKey: "Catalog request failed with HTTP \(status)"
                ])
            }
            let payload = try JSONDecoder().decode(CommunityRegistryPayload.self, from: data)
            self.extensions = payload.extensions
        } catch {
            // Fall back to the catalog copied into the bundle at build time
            // (see scripts/build_native_app.sh) so the app still works offline.
            if let bundled = Self.bundledCatalog() {
                self.extensions = bundled.extensions
            } else {
                self.errorMessage = "Could not fetch catalog: \(error.localizedDescription)"
            }
        }
    }

    private static func bundledCatalog() -> CommunityRegistryPayload? {
        guard let localURL = Bundle.main.url(forResource: "community_registry", withExtension: "json"),
              let localData = try? Data(contentsOf: localURL) else { return nil }
        return try? JSONDecoder().decode(CommunityRegistryPayload.self, from: localData)
    }

    /// Resolve a catalog `download_url` to a package on disk, if one exists.
    ///
    /// Only locations derived at runtime are consulted: the app bundle's own
    /// directory and the current working directory (which is the repository
    /// root when the app is launched from a checkout). Nothing is hardcoded to
    /// a particular developer's machine.
    private static func localPackageURL(for downloadPath: String) -> URL? {
        let fileManager = FileManager.default
        let filename = URL(string: downloadPath)?.lastPathComponent ?? downloadPath
        let cwd = URL(fileURLWithPath: fileManager.currentDirectoryPath)
        let bundleDir = Bundle.main.bundleURL.deletingLastPathComponent()

        var candidates: [URL] = []
        // An absolute or relative path given verbatim in the catalog.
        if downloadPath.hasPrefix("/") {
            candidates.append(URL(fileURLWithPath: downloadPath))
        }
        for root in [cwd, bundleDir] {
            candidates.append(root.appendingPathComponent(downloadPath))
            candidates.append(root.appendingPathComponent("web/packages").appendingPathComponent(filename))
        }

        return candidates.first { fileManager.fileExists(atPath: $0.path) }
    }

    public func downloadAndInstall(extension item: CommunityExtension) async throws -> String {
        guard let downloadStr = item.download_url, !downloadStr.isEmpty else {
            throw NSError(domain: "CommunityRegistry", code: 404, userInfo: [
                NSLocalizedDescriptionKey: "No download URL available for \(item.name)"
            ])
        }

        // 1. Prefer a local copy so running from a checkout needs no network.
        if !downloadStr.hasPrefix("http://"), !downloadStr.hasPrefix("https://"),
           let localURL = Self.localPackageURL(for: downloadStr) {
            return try PackageManager.shared.installPackage(from: localURL, relaunchSafari: true)
        }

        // 2. Resolve the remote URL, treating relative paths as siblings of the catalog.
        let targetURL: URL
        if downloadStr.hasPrefix("http://") || downloadStr.hasPrefix("https://") {
            guard let parsed = URL(string: downloadStr) else {
                throw NSError(domain: "CommunityRegistry", code: 400, userInfo: [
                    NSLocalizedDescriptionKey: "Invalid download URL: \(downloadStr)"
                ])
            }
            targetURL = parsed
        } else {
            guard let resolved = URL(string: downloadStr, relativeTo: RegistryEndpoint.baseURL) else {
                throw NSError(domain: "CommunityRegistry", code: 400, userInfo: [
                    NSLocalizedDescriptionKey: "Could not resolve download path: \(downloadStr)"
                ])
            }
            targetURL = resolved
        }

        let (tempDownloadedURL, response) = try await URLSession.shared.download(from: targetURL)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            let status = (response as? HTTPURLResponse)?.statusCode ?? -1
            throw NSError(domain: "CommunityRegistry", code: status, userInfo: [
                NSLocalizedDescriptionKey: "Download failed with HTTP \(status) from \(targetURL.lastPathComponent)"
            ])
        }

        let packageURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("\(item.id).magicext")
        if FileManager.default.fileExists(atPath: packageURL.path) {
            try? FileManager.default.removeItem(at: packageURL)
        }
        try FileManager.default.moveItem(at: tempDownloadedURL, to: packageURL)
        defer { try? FileManager.default.removeItem(at: packageURL) }

        return try PackageManager.shared.installPackage(from: packageURL, relaunchSafari: true)
    }
}
