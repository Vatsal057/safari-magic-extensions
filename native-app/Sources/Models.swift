import Foundation
import SwiftUI

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
        switch symbolColorName.lowercased() {
        case "purple": return .purple
        case "blue": return .blue
        case "green": return .green
        case "orange": return .orange
        case "pink": return .pink
        case "red": return .red
        case "yellow": return .yellow
        default: return .blue
        }
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

    public var safeSymbol: String {
        selected_symbol ?? "puzzlepiece.extension"
    }

    public var safeColor: Color {
        switch (symbol_color_name ?? "").lowercased() {
        case "purple": return .purple
        case "blue": return .blue
        case "green": return .green
        case "orange": return .orange
        case "pink": return .pink
        case "red": return .red
        case "yellow": return .yellow
        default: return .blue
        }
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
