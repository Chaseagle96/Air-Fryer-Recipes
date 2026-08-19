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
    func fetchVerticals(forceRefresh: Bool) async throws -> [RecipeVertical]
    func fetchFeedManifest(vertical: RecipeVertical, forceRefresh: Bool) async throws -> FeedManifest
    func fetchRecipePage(vertical: RecipeVertical, pageIndex: Int) async throws -> RecipePageEnvelope
}

extension RecipeIntelligenceClient {
    func fetchVerticals() async throws -> [RecipeVertical] {
        try await fetchVerticals(forceRefresh: false)
    }

    func fetchFeedManifest(vertical: RecipeVertical) async throws -> FeedManifest {
        try await fetchFeedManifest(vertical: vertical, forceRefresh: false)
    }
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

    func fetchVerticals(forceRefresh: Bool) async throws -> [RecipeVertical] {
        let requestURL = forceRefresh ? cacheBustedURL(catalogURL, token: UUID().uuidString) : catalogURL
        let catalog: VerticalCatalog = try await request(requestURL, forceRefresh: forceRefresh)
        guard catalog.schemaVersion == 1 else {
            throw RecipeIntelligenceClientError.unsupportedSchema(catalog.schemaVersion)
        }
        return catalog.verticals.filter(\.available)
    }

    func fetchFeedManifest(vertical: RecipeVertical, forceRefresh: Bool) async throws -> FeedManifest {
        if !forceRefresh, let cached = manifestCache[vertical.id] { return cached }

        let requestURL = forceRefresh
            ? cacheBustedURL(vertical.manifestURL, token: UUID().uuidString)
            : vertical.manifestURL
        let manifest: FeedManifest = try await request(requestURL, forceRefresh: forceRefresh)
        guard manifest.schemaVersion == 1 else {
            throw RecipeIntelligenceClientError.unsupportedSchema(manifest.schemaVersion)
        }
        manifestCache[vertical.id] = manifest
        return manifest
    }

    func fetchRecipePage(vertical: RecipeVertical, pageIndex: Int) async throws -> RecipePageEnvelope {
        let manifest = try await fetchFeedManifest(vertical: vertical, forceRefresh: false)
        guard pageIndex >= 0, pageIndex < manifest.pages.count else {
            throw RecipeIntelligenceClientError.pageOutOfRange
        }
        let pageReference = manifest.pages[pageIndex]
        guard let pageURL = URL(string: pageReference.path, relativeTo: vertical.manifestURL)?.absoluteURL else {
            throw RecipeIntelligenceClientError.badResponse
        }

        // Page filenames are intentionally stable. Key the HTTP request by the
        // manifest generation so a newly published ranking snapshot cannot be
        // masked by URLCache or an upstream raw-content cache entry.
        let versionedPageURL = cacheBustedURL(pageURL, token: manifest.generatedAt)
        let page: RecipePageEnvelope = try await request(versionedPageURL, forceRefresh: false)
        guard page.schemaVersion == 1 else {
            throw RecipeIntelligenceClientError.unsupportedSchema(page.schemaVersion)
        }
        return page
    }

    private func request<T: Decodable>(_ url: URL, forceRefresh: Bool) async throws -> T {
        var request = URLRequest(url: url)
        request.cachePolicy = forceRefresh ? .reloadIgnoringLocalCacheData : .reloadRevalidatingCacheData
        request.timeoutInterval = 25
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, 200..<300 ~= http.statusCode else {
            throw RecipeIntelligenceClientError.badResponse
        }
        return try JSONDecoder().decode(T.self, from: data)
    }

    private func cacheBustedURL(_ url: URL, token: String) -> URL {
        guard var components = URLComponents(url: url, resolvingAgainstBaseURL: false) else { return url }
        var items = components.queryItems ?? []
        items.removeAll { $0.name == "ri_version" }
        items.append(URLQueryItem(name: "ri_version", value: token))
        components.queryItems = items
        return components.url ?? url
    }
}

actor PreviewRecipeIntelligenceClient: RecipeIntelligenceClient {
    func fetchVerticals(forceRefresh: Bool) async throws -> [RecipeVertical] { RecipeVertical.fallbacks }

    func fetchFeedManifest(vertical: RecipeVertical, forceRefresh: Bool) async throws -> FeedManifest {
        let recipes = SampleData.recipes.filter { $0.verticalID == vertical.id }
        return FeedManifest(
            schemaVersion: 1,
            generatedAt: "preview",
            vertical: FeedVerticalDescriptor(id: vertical.id, name: vertical.name, sourceCount: 1),
            recipeCount: recipes.count,
            pageSize: max(recipes.count, 1),
            pages: recipes.isEmpty ? [] : [FeedPageReference(index: 1, path: "recipes/0001.json", count: recipes.count)]
        )
    }

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
