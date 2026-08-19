import Foundation

enum RecipeIntelligenceClientError: LocalizedError {
    case badResponse
    case unsupportedSchema(Int)
    case pageOutOfRange

    var errorDescription: String? {
        switch self {
        case .badResponse: return "Recipe Intelligence returned an invalid response."
        case .unsupportedSchema(let version): return "This app does not support Recipe Intelligence schema version \(version)."
        case .pageOutOfRange: return "There are no more recipes in this vertical."
        }
    }
}

protocol RecipeIntelligenceClient: Sendable {
    func fetchVerticals() async throws -> [RecipeVertical]
    func fetchRecipePage(vertical: RecipeVertical, pageIndex: Int) async throws -> RecipePageEnvelope
}

actor LiveRecipeIntelligenceClient: RecipeIntelligenceClient {
    static let catalogURL = URL(string: "https://raw.githubusercontent.com/Chaseagle96/Recipe-Intelligence/main/api/verticals.json")!

    private let session: URLSession
    private let catalogURL: URL
    private var manifestCache: [String: FeedManifest] = [:]

    init(session: URLSession = .shared, catalogURL: URL = LiveRecipeIntelligenceClient.catalogURL) {
        self.session = session
        self.catalogURL = catalogURL
    }

    func fetchVerticals() async throws -> [RecipeVertical] {
        let catalog: VerticalCatalog = try await request(catalogURL)
        guard catalog.schemaVersion == 1 else {
            throw RecipeIntelligenceClientError.unsupportedSchema(catalog.schemaVersion)
        }
        return catalog.verticals.filter(\.available)
    }

    func fetchRecipePage(vertical: RecipeVertical, pageIndex: Int) async throws -> RecipePageEnvelope {
        let manifest = try await manifest(for: vertical)
        guard pageIndex >= 0, pageIndex < manifest.pages.count else {
            throw RecipeIntelligenceClientError.pageOutOfRange
        }
        let pageReference = manifest.pages[pageIndex]
        guard let pageURL = URL(string: pageReference.path, relativeTo: vertical.manifestURL)?.absoluteURL else {
            throw RecipeIntelligenceClientError.badResponse
        }
        let page: RecipePageEnvelope = try await request(pageURL)
        guard page.schemaVersion == 1 else {
            throw RecipeIntelligenceClientError.unsupportedSchema(page.schemaVersion)
        }
        return page
    }

    private func manifest(for vertical: RecipeVertical) async throws -> FeedManifest {
        if let cached = manifestCache[vertical.id] { return cached }
        let manifest: FeedManifest = try await request(vertical.manifestURL)
        guard manifest.schemaVersion == 1 else {
            throw RecipeIntelligenceClientError.unsupportedSchema(manifest.schemaVersion)
        }
        manifestCache[vertical.id] = manifest
        return manifest
    }

    private func request<T: Decodable>(_ url: URL) async throws -> T {
        var request = URLRequest(url: url)
        request.cachePolicy = .reloadRevalidatingCacheData
        request.timeoutInterval = 25
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, 200..<300 ~= http.statusCode else {
            throw RecipeIntelligenceClientError.badResponse
        }
        return try JSONDecoder().decode(T.self, from: data)
    }
}

actor PreviewRecipeIntelligenceClient: RecipeIntelligenceClient {
    func fetchVerticals() async throws -> [RecipeVertical] { RecipeVertical.fallbacks }

    func fetchRecipePage(vertical: RecipeVertical, pageIndex: Int) async throws -> RecipePageEnvelope {
        guard pageIndex == 0 else { throw RecipeIntelligenceClientError.pageOutOfRange }
        let recipes = SampleData.recipes.filter { $0.verticalID == vertical.id }
        return RecipePageEnvelope(
            schemaVersion: 1,
            generatedAt: "preview",
            verticalID: vertical.id,
            verticalName: vertical.name,
            page: 1,
            recipes: recipes
        )
    }
}
