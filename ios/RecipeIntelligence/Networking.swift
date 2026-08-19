import Foundation

enum RecipeIntelligenceClientError: LocalizedError {
    case badResponse
    case unsupportedSchema(Int)
    case pageOutOfRange
    case inconsistentSnapshot
    case nonAuthoritativeFeed(String)

    var errorDescription: String? {
        switch self {
        case .badResponse: return "Recipe Intelligence returned an invalid response."
        case .unsupportedSchema(let version): return "This app does not support Recipe Intelligence schema version \(version)."
        case .pageOutOfRange: return "There are no more recipes in this vertical."
        case .inconsistentSnapshot: return "Recipe Intelligence updated while this refresh was loading. The current recipes were kept and the app will retry."
        case .nonAuthoritativeFeed(let status): return "Recipe Intelligence is refreshing this ranking and has not certified the current generation yet (\(status))."
        }
    }
}

private struct FeedAuthorityEnvelope: Decodable {
    let authoritative: Bool
    let status: String
    let authorityContractVersion: Int
    let rankingGeneratedAt: String?

    enum CodingKeys: String, CodingKey {
        case authoritative, status
        case authorityContractVersion = "authority_contract_version"
        case rankingGeneratedAt = "ranking_generated_at"
    }
}

protocol RecipeIntelligenceClient: Sendable {
    func fetchVerticals(forceRefresh: Bool) async throws -> [RecipeVertical]
    func fetchFeedManifest(vertical: RecipeVertical, forceRefresh: Bool) async throws -> FeedManifest
    func fetchRecipePage(vertical: RecipeVertical, pageIndex: Int) async throws -> RecipePageEnvelope
    func fetchCorpusPage(vertical: RecipeVertical, pageIndex: Int) async throws -> RecipePageEnvelope
}

extension RecipeIntelligenceClient {
    func fetchVerticals() async throws -> [RecipeVertical] {
        try await fetchVerticals(forceRefresh: false)
    }

    func fetchFeedManifest(vertical: RecipeVertical) async throws -> FeedManifest {
        try await fetchFeedManifest(vertical: vertical, forceRefresh: false)
    }

    // Test doubles and older clients can continue treating the ranked feed as the
    // corpus until they explicitly implement the broader mobile contract.
    func fetchCorpusPage(vertical: RecipeVertical, pageIndex: Int) async throws -> RecipePageEnvelope {
        try await fetchRecipePage(vertical: vertical, pageIndex: pageIndex)
    }
}

actor LiveRecipeIntelligenceClient: RecipeIntelligenceClient {
    static let catalogURL = URL(string: "https://raw.githubusercontent.com/Chaseagle96/Recipe-Intelligence/main/api/verticals.json")!
    private static let authorityContractVersion = 2

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
        if !forceRefresh, let cached = manifestCache[vertical.id] {
            try await assertAuthoritative(vertical: vertical, manifest: cached)
            return cached
        }

        let requestURL = forceRefresh
            ? cacheBustedURL(vertical.manifestURL, token: UUID().uuidString)
            : vertical.manifestURL
        let manifest: FeedManifest = try await request(requestURL, forceRefresh: forceRefresh)
        guard manifest.schemaVersion == 1 else {
            throw RecipeIntelligenceClientError.unsupportedSchema(manifest.schemaVersion)
        }
        guard manifest.vertical.id == vertical.id else {
            throw RecipeIntelligenceClientError.badResponse
        }
        try await assertAuthoritative(vertical: vertical, manifest: manifest)
        manifestCache[vertical.id] = manifest
        return manifest
    }

    func fetchRecipePage(vertical: RecipeVertical, pageIndex: Int) async throws -> RecipePageEnvelope {
        let manifest = try await fetchFeedManifest(vertical: vertical, forceRefresh: false)
        return try await fetchPage(
            vertical: vertical,
            pageIndex: pageIndex,
            references: manifest.pages,
            manifest: manifest
        )
    }

    func fetchCorpusPage(vertical: RecipeVertical, pageIndex: Int) async throws -> RecipePageEnvelope {
        let manifest = try await fetchFeedManifest(vertical: vertical, forceRefresh: false)
        return try await fetchPage(
            vertical: vertical,
            pageIndex: pageIndex,
            references: manifest.effectiveCorpusPages,
            manifest: manifest
        )
    }

    private func assertAuthoritative(vertical: RecipeVertical, manifest: FeedManifest) async throws {
        guard let authorityURL = URL(string: "authority.json", relativeTo: vertical.manifestURL)?.absoluteURL else {
            throw RecipeIntelligenceClientError.badResponse
        }
        let versionedAuthorityURL = cacheBustedURL(authorityURL, token: UUID().uuidString)
        let authority: FeedAuthorityEnvelope = try await request(versionedAuthorityURL, forceRefresh: true)
        guard authority.authorityContractVersion == Self.authorityContractVersion else {
            throw RecipeIntelligenceClientError.nonAuthoritativeFeed("unsupported_authority_contract")
        }
        guard authority.authoritative else {
            throw RecipeIntelligenceClientError.nonAuthoritativeFeed(authority.status)
        }
        guard let rankingGeneratedAt = authority.rankingGeneratedAt,
              rankingGeneratedAt == manifest.generatedAt else {
            throw RecipeIntelligenceClientError.inconsistentSnapshot
        }
    }

    private func fetchPage(
        vertical: RecipeVertical,
        pageIndex: Int,
        references: [FeedPageReference],
        manifest: FeedManifest
    ) async throws -> RecipePageEnvelope {
        guard pageIndex >= 0, pageIndex < references.count else {
            throw RecipeIntelligenceClientError.pageOutOfRange
        }
        let pageReference = references[pageIndex]
        guard let pageURL = URL(string: pageReference.path, relativeTo: vertical.manifestURL)?.absoluteURL else {
            throw RecipeIntelligenceClientError.badResponse
        }

        // Page filenames are intentionally stable. Key the HTTP request by the
        // manifest generation so a newly published snapshot cannot be masked by
        // URLCache or an upstream raw-content cache entry.
        let versionedPageURL = cacheBustedURL(pageURL, token: manifest.generatedAt)
        let page: RecipePageEnvelope = try await request(versionedPageURL, forceRefresh: false)
        guard page.schemaVersion == 1 else {
            throw RecipeIntelligenceClientError.unsupportedSchema(page.schemaVersion)
        }
        guard page.verticalID == vertical.id else {
            throw RecipeIntelligenceClientError.badResponse
        }
        guard page.generatedAt == manifest.generatedAt else {
            // `main` can advance between the manifest and page HTTP requests.
            // Never mix two generations into one client snapshot.
            throw RecipeIntelligenceClientError.inconsistentSnapshot
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
        try page(vertical: vertical, pageIndex: pageIndex)
    }

    func fetchCorpusPage(vertical: RecipeVertical, pageIndex: Int) async throws -> RecipePageEnvelope {
        try page(vertical: vertical, pageIndex: pageIndex)
    }

    private func page(vertical: RecipeVertical, pageIndex: Int) throws -> RecipePageEnvelope {
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
