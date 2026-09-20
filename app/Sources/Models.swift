import Foundation
import SwiftUI

/// Maps the colour names used by the registry and Safari's database onto
/// SwiftUI colours.
///
/// The accepted names are the options offered by the submission form in
/// `.github/ISSUE_TEMPLATE/extension_submission.yml`, so keep the two in sync.
public enum MagicColor {
    public static func named(_ name: String?) -> Color {
        switch (name ?? "").lowercased() {
        case "purple": return .purple
        case "blue": return .blue
        case "green": return .green
        case "orange": return .orange
        case "pink": return .pink
        case "red": return .red
        case "yellow": return .yellow
        case "gray", "grey": return .gray
        default: return .blue
        }
    }
}

public struct InstalledExtension: Identifiable, Hashable {
    public let id: String
    public let name: String
    public let directoryName: String
    public let folderPath: String
    public let existsOnDisk: Bool
    public let selectedSymbol: String
    public let symbolColorName: String
    public let prompt: String
    public let description: String
    public let creationDate: Date
    public let modifiedDate: Date

    public var color: Color {
        MagicColor.named(symbolColorName)
    }
}

public struct CommunityExtension: Identifiable, Codable, Hashable {
    public let id: String
    public let name: String
    public let author: String?
    public let version: String?
    public let description: String?
    public let prompt: String?
    public let selected_symbol: String?
    public let symbol_color_name: String?
    public let tags: [String]?
    public let download_url: String?
    // Presentation fields curated in web/registry_curation.json. Optional so
    // the app keeps decoding older catalogs that predate them.
    public let category: String?
    public let art_image: String?
    public let featured: Bool?

    public var safeSymbol: String {
        selected_symbol ?? "puzzlepiece.extension"
    }

    public var safeColor: Color {
        MagicColor.named(symbol_color_name)
    }
}

public struct CommunityRegistryPayload: Codable {
    public let version: Int
    public let registry_name: String?
    public let updated_at: String?
    public let extensions: [CommunityExtension]
}

public struct MagicPackageMeta: Codable {
    public let magic_format_version: Int?
    public let id: String?
    public let name: String?
    public let author: String?
    public let version: String?
    public let description: String?
    public let prompt: String?
    public let selected_symbol: String?
    public let symbol_color_name: String?
    public let packaged_at: String?
}
