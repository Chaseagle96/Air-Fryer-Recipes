import SwiftUI

struct DiscoverView: View {
    @EnvironmentObject private var appModel: AppModel
    @State private var detailRecipe: RemoteRecipe?

    var body: some View {
        GeometryReader { proxy in
            ScrollView(.vertical, showsIndicators: false) {
                VStack(spacing: 12) {
                    verticalSelector
                    refreshStatus

                    if appModel.isLoading && appModel.deck.isEmpty {
                        Spacer(minLength: 120)
                        ProgressView("Finding great recipes…")
                        Spacer(minLength: 120)
                    } else if let recipe = appModel.deck.first {
                        deck(recipe)
                            .frame(height: max(520, proxy.size.height - 90))
                            .task(id: recipe.recipeID) { await appModel.prefetchIfNeeded(recipe) }
                    } else {
                        emptyState
                            .frame(minHeight: max(460, proxy.size.height - 110))
                    }
                }
                .frame(maxWidth: .infinity)
                .frame(minHeight: proxy.size.height, alignment: .top)
                .padding(.horizontal)
            }
            .refreshable {
                await appModel.refreshCurrentFeed(trigger: .manual)
            }
        }
        .navigationTitle("Discover")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItemGroup(placement: .topBarTrailing) {
                if appModel.canUndo {
                    Button("Undo", systemImage: "arrow.uturn.backward") { appModel.undoLastDecision() }
                        .accessibilityIdentifier("discover.undo")
                }
                Button {
                    Task { await appModel.refreshCurrentFeed(trigger: .manual) }
                } label: {
                    Label("Refresh rankings", systemImage: "arrow.clockwise")
                }
                .disabled(appModel.isRefreshingFeed || appModel.isLoading)
                .accessibilityIdentifier("discover.refresh")
                .accessibilityValue(appModel.isRefreshingFeed ? "Refreshing" : "")
            }
        }
        .sheet(item: $detailRecipe) { recipe in
            NavigationStack { RemoteRecipeDetailView(recipe: recipe) }
        }
        .animation(.snappy, value: appModel.deck.first?.recipeID)
    }

    @ViewBuilder
    private var refreshStatus: some View {
        if appModel.isRefreshingFeed {
            Label("Checking for new rankings…", systemImage: "arrow.triangle.2.circlepath")
                .accessibilityIdentifier("discover.refreshStatus")
        } else if let message = appModel.feedStatusMessage {
            Text(message)
                .accessibilityIdentifier("discover.refreshStatus")
        }
    }

    private var verticalSelector: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(appModel.verticals) { vertical in
                    Button {
                        Task { await appModel.selectVertical(vertical) }
                    } label: {
                        Label(vertical.name, systemImage: vertical.icon)
                            .font(.subheadline.weight(.semibold))
                            .padding(.horizontal, 14)
                            .padding(.vertical, 9)
                            .background(appModel.selectedVertical?.id == vertical.id ? Color.accentColor.opacity(0.18) : Color.secondary.opacity(0.10), in: Capsule())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Explore \(vertical.name) recipes")
                    .accessibilityAddTraits(appModel.selectedVertical?.id == vertical.id ? .isSelected : [])
                    .accessibilityIdentifier("vertical.\(vertical.id)")
                }
            }
            .padding(.vertical, 2)
        }
    }

    @ViewBuilder
    private func deck(_ topRecipe: RemoteRecipe) -> some View {
        VStack(spacing: 14) {
            ZStack {
                ForEach(Array(appModel.deck.prefix(3).enumerated()).reversed(), id: \.element.recipeID) { index, recipe in
                    RecipeCardView(
                        recipe: recipe,
                        isTop: index == 0,
                        onDecision: { decision in appModel.handleDecision(decision, recipe: recipe) },
                        onDetails: {
                            appModel.recordOpened(recipe)
                            detailRecipe = recipe
                        }
                    )
                    .scaleEffect(1 - CGFloat(index) * 0.035)
                    .offset(y: CGFloat(index) * 8)
                    .zIndex(Double(10 - index))
                }
            }
            .frame(maxHeight: .infinity)

            HStack(spacing: 16) {
                actionButton("Skip", systemImage: "xmark", identifier: "discover.skip") {
                    appModel.handleDecision(.skip, recipe: topRecipe)
                }
                actionButton("Not Now", systemImage: "clock", identifier: "discover.notNow") {
                    appModel.handleDecision(.notNow, recipe: topRecipe)
                }
                actionButton("Save", systemImage: "heart.fill", identifier: "discover.save", prominent: true) {
                    appModel.handleDecision(.save, recipe: topRecipe)
                }
                actionButton("Details", systemImage: "info.circle", identifier: "discover.details") {
                    appModel.recordOpened(topRecipe)
                    detailRecipe = topRecipe
                }
            }
            .frame(maxWidth: .infinity)
        }
    }

    @ViewBuilder
    private func actionButton(
        _ title: String,
        systemImage: String,
        identifier: String,
        prominent: Bool = false,
        action: @escaping () -> Void
    ) -> some View {
        if prominent {
            Button(action: action) {
                actionButtonLabel(title, systemImage: systemImage)
            }
            .buttonStyle(.borderedProminent)
            .accessibilityIdentifier(identifier)
        } else {
            Button(action: action) {
                actionButtonLabel(title, systemImage: systemImage)
            }
            .buttonStyle(.bordered)
            .accessibilityIdentifier(identifier)
        }
    }

    private func actionButtonLabel(_ title: String, systemImage: String) -> some View {
        VStack(spacing: 5) {
            Image(systemName: systemImage).font(.title2)
            Text(title).font(.caption.weight(.semibold))
        }
        .frame(maxWidth: .infinity, minHeight: 56)
    }

    private var emptyState: some View {
        ContentUnavailableView {
            Label("You’re caught up", systemImage: "checkmark.circle")
        } description: {
            Text(appModel.errorMessage ?? "Try another vertical, or come back after Recipe Intelligence finds more recipes.")
        } actions: {
            Button("Try Again") { Task { await appModel.retry() } }
        }
        .frame(maxHeight: .infinity)
    }
}

private struct RecipeCardView: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let recipe: RemoteRecipe
    let isTop: Bool
    let onDecision: (RecipeDecision) -> Void
    let onDetails: () -> Void
    @State private var offset: CGSize = .zero

    var body: some View {
        GeometryReader { proxy in
            VStack(spacing: 0) {
                RemoteRecipeImage(url: recipe.photoURL, title: recipe.title)
                    .frame(height: min(370, proxy.size.height * 0.60))
                    .clipped()
                    .overlay(alignment: .topLeading) {
                        Text("#\(recipe.rank) \(recipe.verticalName)")
                            .font(.caption.weight(.bold))
                            .padding(.horizontal, 10)
                            .padding(.vertical, 7)
                            .background(.ultraThinMaterial, in: Capsule())
                            .padding(12)
                    }

                VStack(alignment: .leading, spacing: 10) {
                    Text(recipe.title)
                        .font(.title2.bold())
                        .lineLimit(3)
                        .minimumScaleFactor(0.8)

                    HStack(spacing: 12) {
                        Label(String(format: "%.1f", recipe.rating), systemImage: "star.fill")
                        Text("\(recipe.ratingCount.formatted()) ratings")
                        if !recipe.evidenceGrade.isEmpty { Text("Evidence \(recipe.evidenceGrade)") }
                    }
                    .font(.subheadline)
                    .foregroundStyle(.secondary)

                    Text(recipe.source)
                        .font(.subheadline.weight(.medium))
                    if !recipe.categories.isEmpty {
                        Text(recipe.categories.prefix(3).joined(separator: " · "))
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                    Text(recipe.confidenceLabel)
                        .font(.footnote.weight(.semibold))
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(16)
            }
            .background(.background)
            .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
            .shadow(color: .black.opacity(0.12), radius: 18, y: 8)
            .overlay(alignment: offset.width >= 40 ? .topLeading : .topTrailing) {
                if isTop && abs(offset.width) >= 40 {
                    Text(offset.width > 0 ? "SAVE" : "NOPE")
                        .font(.title.bold())
                        .foregroundStyle(offset.width > 0 ? .green : .red)
                        .padding(24)
                        .rotationEffect(.degrees(offset.width > 0 ? -8 : 8))
                }
            }
            .offset(offset)
            .rotationEffect(.degrees(isTop ? Double(offset.width / 24) : 0))
            .contentShape(Rectangle())
            .onTapGesture { if isTop { onDetails() } }
            .gesture(dragGesture, including: isTop ? .all : .none)
        }
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(recipe.title). Recipe Intelligence rank \(recipe.rank) in \(recipe.verticalName). Rating \(String(format: "%.1f", recipe.rating)) from \(recipe.ratingCount) ratings. \(recipe.confidenceLabel).")
        .accessibilityHint("Swipe right to save or left to skip. The buttons below provide the same actions.")
        .accessibilityAction(named: "Save") { onDecision(.save) }
        .accessibilityAction(named: "Skip") { onDecision(.skip) }
        .accessibilityAction(named: "Not Now") { onDecision(.notNow) }
        .accessibilityAction(named: "Details") { onDetails() }
    }

    private var dragGesture: some Gesture {
        DragGesture(minimumDistance: 16)
            .onChanged { value in offset = value.translation }
            .onEnded { value in
                let threshold: CGFloat = 120
                if value.translation.width > threshold {
                    complete(.save)
                } else if value.translation.width < -threshold {
                    complete(.skip)
                } else {
                    if reduceMotion { offset = .zero }
                    else { withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) { offset = .zero } }
                }
            }
    }

    private func complete(_ decision: RecipeDecision) {
        if reduceMotion {
            offset = .zero
            onDecision(decision)
        } else {
            withAnimation(.easeOut(duration: 0.18)) { offset.width = decision == .save ? 700 : -700 }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.16) { onDecision(decision); offset = .zero }
        }
    }
}
