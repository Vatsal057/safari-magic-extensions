import Foundation
import SQLite3

public final class ExtensionDatabase {
    public static let shared = ExtensionDatabase()

    public static let realHomeDir: URL = {
        if let pw = getpwuid(getuid()), let dir = pw.pointee.pw_dir {
            return URL(fileURLWithPath: String(cString: dir))
        }
        return FileManager.default.homeDirectoryForCurrentUser
    }()

    public static let magicExtensionsDir: URL = {
        realHomeDir.appendingPathComponent("Library/Containers/com.apple.Safari/Data/Library/Safari/MagicExtensions")
    }()

    public static let dbPath: URL = {
        magicExtensionsDir.appendingPathComponent("Extensions.db")
    }()

    private let macAbsoluteTimeOffset: Double = 978307200.0

    private init() {}

    private func openDatabase(readOnly: Bool = false) throws -> OpaquePointer? {
        var db: OpaquePointer?
        let path = Self.dbPath.path
        if !FileManager.default.fileExists(atPath: path) {
            throw NSError(domain: "ExtensionDatabase", code: 404, userInfo: [
                NSLocalizedDescriptionKey: "Extensions.db not found at \(path). Please launch Safari at least once."
            ])
        }

        let flags = readOnly
            ? (SQLITE_OPEN_READONLY | SQLITE_OPEN_FULLMUTEX)
            : (SQLITE_OPEN_READWRITE | SQLITE_OPEN_CREATE | SQLITE_OPEN_FULLMUTEX)

        let rc = sqlite3_open_v2(path, &db, flags, nil)
        if rc != SQLITE_OK {
            let errmsg = db != nil ? String(cString: sqlite3_errmsg(db)) : "Code \(rc)"
            if let db = db { sqlite3_close(db) }

            // If readwrite failed, try readonly fallback
            if !readOnly {
                return try openDatabase(readOnly: true)
            }

            throw NSError(domain: "ExtensionDatabase", code: Int(rc), userInfo: [
                NSLocalizedDescriptionKey: "Failed to open SQLite database: \(errmsg)"
            ])
        }

        sqlite3_busy_timeout(db, 3000)
        return db
    }

public struct ExtensionFetchResult {
    public let extensions: [InstalledExtension]
    public let error: String?
    public let isPermissionDenied: Bool
}

    public func fetchInstalledExtensionsWithStatus() -> ExtensionFetchResult {
        var db: OpaquePointer?
        do {
            db = try openDatabase(readOnly: true)
        } catch {
            let desc = error.localizedDescription
            let isPerm = desc.localizedCaseInsensitiveContains("authorization denied") ||
                         desc.localizedCaseInsensitiveContains("operation not permitted") ||
                         desc.localizedCaseInsensitiveContains("permission")
            return ExtensionFetchResult(extensions: [], error: desc, isPermissionDenied: isPerm)
        }
        defer { if let db = db { sqlite3_close(db) } }

        let query = """
        SELECT id, name, directory_name, selected_symbol, symbol_color_name,
               prompt, description, creation_date, modified_date
        FROM magic_extensions
        WHERE name != ''
        ORDER BY modified_date DESC;
        """

        var stmt: OpaquePointer?
        var results: [InstalledExtension] = []

        if sqlite3_prepare_v2(db, query, -1, &stmt, nil) == SQLITE_OK {
            while sqlite3_step(stmt) == SQLITE_ROW {
                let id = String(cString: sqlite3_column_text(stmt, 0))
                let name = String(cString: sqlite3_column_text(stmt, 1))
                let directoryName = String(cString: sqlite3_column_text(stmt, 2))
                let selectedSymbol = String(cString: sqlite3_column_text(stmt, 3))
                let symbolColorName = String(cString: sqlite3_column_text(stmt, 4))
                let prompt = sqlite3_column_text(stmt, 5).map { String(cString: $0) } ?? ""
                let description = sqlite3_column_text(stmt, 6).map { String(cString: $0) } ?? ""
                let creationSecs = sqlite3_column_double(stmt, 7) + macAbsoluteTimeOffset
                let modifiedSecs = sqlite3_column_double(stmt, 8) + macAbsoluteTimeOffset

                let folder = Self.magicExtensionsDir.appendingPathComponent(directoryName)
                let exists = FileManager.default.fileExists(atPath: folder.path)

                results.append(InstalledExtension(
                    id: id,
                    name: name,
                    directoryName: directoryName,
                    folderPath: folder.path,
                    existsOnDisk: exists,
                    selectedSymbol: selectedSymbol.isEmpty ? "puzzlepiece.extension" : selectedSymbol,
                    symbolColorName: symbolColorName.isEmpty ? "blue" : symbolColorName,
                    prompt: prompt,
                    description: description,
                    creationDate: Date(timeIntervalSince1970: creationSecs),
                    modifiedDate: Date(timeIntervalSince1970: modifiedSecs)
                ))
            }
        } else {
            let err = String(cString: sqlite3_errmsg(db))
            sqlite3_finalize(stmt)
            let isPerm = err.localizedCaseInsensitiveContains("authorization denied") ||
                         err.localizedCaseInsensitiveContains("operation not permitted")
            return ExtensionFetchResult(extensions: [], error: "Query prepare failed: \(err)", isPermissionDenied: isPerm)
        }
        sqlite3_finalize(stmt)
        return ExtensionFetchResult(extensions: results, error: nil, isPermissionDenied: false)
    }

    public func fetchInstalledExtensions() -> [InstalledExtension] {
        return fetchInstalledExtensionsWithStatus().extensions
    }

    public func registerExtension(
        name: String,
        directoryName: String,
        symbol: String,
        color: String,
        prompt: String,
        description: String
    ) throws -> String {
        guard let db = try openDatabase(readOnly: false) else {
            throw NSError(domain: "ExtensionDatabase", code: 500, userInfo: [NSLocalizedDescriptionKey: "Cannot open DB for writing"])
        }
        defer { sqlite3_close(db) }

        // Fetch next sync generation
        var nextGen: Int = 1
        var syncStmt: OpaquePointer?
        if sqlite3_prepare_v2(db, "SELECT value FROM metadata WHERE key = 'next_sync_generation';", -1, &syncStmt, nil) == SQLITE_OK {
            if sqlite3_step(syncStmt) == SQLITE_ROW {
                if let valStr = sqlite3_column_text(syncStmt, 0) {
                    nextGen = Int(String(cString: valStr)) ?? 1
                }
            }
        }
        sqlite3_finalize(syncStmt)

        let extId = UUID().uuidString.uppercased()
        let appleNow = Date().timeIntervalSince1970 - macAbsoluteTimeOffset

        let insertSQL = """
        INSERT INTO magic_extensions (
            id, version, creation_date, modified_date, name, description,
            selected_symbol, prompt, directory_name, symbol_color_name,
            sync_state, sync_generation
        ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?);
        """

        var insertStmt: OpaquePointer?
        guard sqlite3_prepare_v2(db, insertSQL, -1, &insertStmt, nil) == SQLITE_OK else {
            let err = String(cString: sqlite3_errmsg(db))
            throw NSError(domain: "ExtensionDatabase", code: 500, userInfo: [NSLocalizedDescriptionKey: err])
        }

        let SQLITE_TRANSIENT = unsafeBitCast(-1, to: sqlite3_destructor_type.self)
        sqlite3_bind_text(insertStmt, 1, extId, -1, SQLITE_TRANSIENT)
        sqlite3_bind_double(insertStmt, 2, appleNow)
        sqlite3_bind_double(insertStmt, 3, appleNow)
        sqlite3_bind_text(insertStmt, 4, name, -1, SQLITE_TRANSIENT)
        sqlite3_bind_text(insertStmt, 5, description, -1, SQLITE_TRANSIENT)
        sqlite3_bind_text(insertStmt, 6, symbol, -1, SQLITE_TRANSIENT)
        sqlite3_bind_text(insertStmt, 7, prompt, -1, SQLITE_TRANSIENT)
        sqlite3_bind_text(insertStmt, 8, directoryName, -1, SQLITE_TRANSIENT)
        sqlite3_bind_text(insertStmt, 9, color, -1, SQLITE_TRANSIENT)
        sqlite3_bind_int(insertStmt, 10, Int32(nextGen))

        if sqlite3_step(insertStmt) != SQLITE_DONE {
            let err = String(cString: sqlite3_errmsg(db))
            sqlite3_finalize(insertStmt)
            throw NSError(domain: "ExtensionDatabase", code: 500, userInfo: [NSLocalizedDescriptionKey: err])
        }
        sqlite3_finalize(insertStmt)

        // Bump sync generation
        var bumpStmt: OpaquePointer?
        if sqlite3_prepare_v2(db, "UPDATE metadata SET value = ? WHERE key = 'next_sync_generation';", -1, &bumpStmt, nil) == SQLITE_OK {
            let nextStr = String(nextGen + 1)
            sqlite3_bind_text(bumpStmt, 1, nextStr, -1, SQLITE_TRANSIENT)
            _ = sqlite3_step(bumpStmt)
        }
        sqlite3_finalize(bumpStmt)

        return extId
    }
}
