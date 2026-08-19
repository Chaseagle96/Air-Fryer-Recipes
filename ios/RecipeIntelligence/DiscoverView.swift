import SwiftUI

struct DiscoverView: View {
    @EnvironmentObject private var appModel: AppModel
    @AppStorage("discover.dismissedFeedStatusMessage") private var dismissedFeedStatusMessage = ""
    @State private var detailRecipe: RemoteRecipe?

    var body: some View {
        GeometryReader { proxy in
            ScrollView(.vertical, showsIndicators: false) {
                VStack(spacing: 14) {
                    verticalSelector
                    refreshStatus

                    if appModel.isLoading && appModel.deck.isEmpty {
                        Spacer(minLength: 120)
                        ProgressView("Finding great recipes…")
                            .controlSize(.large)
                        Spacer(minLength: 120)
                    } else if let recipe = appModel.deck.first {
                        deck(recipe)
                            .task(id: recipe.recipeID) { await appModel.prefetchIfNeeded(recipe) }
                    } else {
                        emptyState
                            .frame(minHeight: max(460, proxy.size.height - 110))
                    }
                }
                .frame(maxWidth: .infinity)
                .frame(minHeight: proxy.size.height, alignment: .top)
                .padding(.horizontal)
                .padding(.bottom, 88)
            }
            .refreshable {
                await appModel.refreshCurrentFeed(trigger: .manual)
            }
        }
        .recipeScreenBackground()
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
        .recipeToolbarBehavior()
    }

    @ViewBuilder
    private var refreshStatus: some View {
        if appModel.isRefreshingFeed {
            Label("Checking for new rankings…", systemImage: "arrow.triangle.2.circlepath")
                .font(.footnote.weight(.semibold))
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .recipeGlassSurface(cornerRadius: 16)
                .accessibilityIdentifier("discover.refreshStatus")
        } else if let message = appModel.feedStatusMessage,
                  message != dismissedFeedStatusMessage {
            HStack(spacing: 10) {
                Text(message)
                    .font(.footnote.weight(.medium))
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)

                Button {
                    dismissedFeedStatusMessage = message
                } label: {
                    Image(systemName: "xmark")
                        .font(.caption.bold())
                        .frame(width: 28, height: 28)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Dismiss ranking notice")
                .accessibilityIdentifier("discover.dismissRefreshStatus")
            }
            .padding(.leading, 12)
            .padding(.trailing, 6)
            .padding(.vertical, 6)
            .recipeGlassSurface(cornerRadius: 16)
            .accessibilityIdentifier("discover.refreshStatus")
        }
    }

    private var verticalSelector: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            RecipeGlassGroup(spacing: 8) {
                HStack(spacing: 8) {
                    ForEach(appModel.verticals) { vertical in
                        let selected = appModel.selectedVertical?.id == vertical.id
                        Button {
                            Task { await appModel.selectVertical(vertical) }
                        } label: {
                            Label(vertical.name, systemImage: vertical.icon)
                                .font(.subheadline.weight(.semibold))
                                .padding(.horizontal, 14)
                                .padding(.vertical, 10)
                                .recipeGlassSurface(
                                    cornerRadius: 18,
                                    tint: selected ? RecipeDesign.accent.opacity(0.28) : nil,
                                    interactive: true
                                )
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Explore \(vertical.name) recipes")
                        .accessibilityAddTraits(selected ? .isSelected : [])
                        .accessibilityIdentifier("vertical.\(vertical.id)")
                    }
                }
            }
            .padding(.vertical, 4)
        }
    }

    private func deck(_ topRecipe: RemoteRecipe) -> some View {
        RecipeCardView(
            recipe: topRecipe,
            onDecision: { decision in appModel.handleDecision(decision, recipe: topRecipe) },
            onDetails: {
                appModel.recordOpened(topRecipe)
                detailRecipe = topRecipe
            }
        )
        .frame(maxWidth: .infinity)
        .clipped()
    }

    private var emptyState: some View {
        ContentUnavailableView {
            Label("You’re caught up", systemImage: "checkmark.circle")
        } description: {
            Text(appModel.errorMessage ?? "Try another vertical, or come back after Recipe Intelligence finds more recipes.")
        } actions: {
            Button("Try Again") { Task { await appModel.retry() } }
                .recipeGlassButton(prominent: true)
        }
        .frame(maxHeight: .infinity)
    }
}

private struct RecipeCardView: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    let recipe: RemoteRecipe
    let onDecision: (RecipeDecision) -> Void
    let onDetails: () -> Void
    @State private var offset: CGSize = .zero

    var body: some View {
        VStack(spacing: 0) {
            RemoteRecipeImage(url: recipe.photoURL, title: recipe.title)
                .frame(maxWidth: .infinity)
                .aspectRatio(1.18, contentMode: .fill)
                .clipped()
                .overlay(alignment: .topLeading) {
                    Text("#\(recipe.rank) \(recipe.verticalName)")
                        .font(.caption.weight(.bold))
                        .padding(.horizontal, 11)
                        .padding(.vertical, 8)
                        .recipeGlassSurface(cornerRadius: 18)
                        .padding(12)
                }

            VStack(alignment: .leading, spacing: 10) {
                Text(recipe.title)
                    .font(.title2.bold())
                    .lineLimit(3)
                    .minimumScaleFactor(0.82)
                    .fixedSize(horizontal: false, vertical: true)

                Text(metricSummary)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)

                Text(recipe.source)
                    .font(.subheadline.weight(.medium))
                    .lineLimit(1)
                    .truncationMode(.middle)

                if !recipe.categories.isEmpty {
                    Text(recipe.categories.prefix(3).joined(separator: " · "))
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .lineLimit(2)
                }

                Text(recipe.confidenceLabel)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(16)
        }
        .frame(maxWidth: .infinity)
        .recipeGlassSurface(cornerRadius: 30, interactive: true)
        .clipShape(RoundedRectangle(cornerRadius: 30, style: .continuous))
        .shadow(color: .black.opacity(0.08), radius: 14, y: 7)
        .overlay(alignment: offset.width >= 40 ? .topLeading : .topTrailing) {
            if abs(offset.width) >= 40 {
                Text(offset.width > 0 ? "SAVE" : "NOPE")
                    .font(.title.bold())
                    .foregroundStyle(offset.width > 0 ? .green : .red)
                    .padding(24)
                    .rotationEffect(.degrees(offset.width > 0 ? -8 : 8))
            }
        }
        .offset(x: offset.width)
        .rotationEffect(.degrees(Double(offset.width / 24)))
        .contentShape(Rectangle())
        .onTapGesture { onDetails() }
        .simultaneousGesture(dragGesture)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(recipe.title). Recipe Intelligence rank \(recipe.rank) in \(recipe.verticalName). Rating \(String(format: "%.1f", recipe.rating)) from \(recipe.ratingCount) ratings. \(recipe.confidenceLabel).")
        .accessibilityHint("Swipe right to save or left to skip. Activate the card for details.")
        .accessibilityAction(named: "Save") { onDecision(.save) }
        .accessibilityAction(named: "Skip") { onDecision(.skip) }
        .accessibilityAction(named: "Not Now") { onDecision(.notNow) }
        .accessibilityAction(named: "Details") { onDetails() }
    }

    private var metricSummary: String {
        var parts = [
            "★ \(String(format: "%.1f", recipe.rating))",
            "\(recipe.ratingCount.formatted()) ratings"
        ]
        if !recipe.evidenceGrade.isEmpty {
            parts.append("Evidence \(recipe.evidenceGrade)")
        }
        return parts.joined(separator: " · ")
    }

    private var dragGesture: some Gesture {
        DragGesture(minimumDistance: 16)
            .onChanged { value in
                guard abs(value.translation.width) > abs(value.translation.height) else { return }
                offset = CGSize(width: value.translation.width, height: 0)
            }
            .onEnded { value in
                let threshold: CGFloat = 110
                guard abs(value.translation.width) > abs(value.translation.height) else {
                    resetOffset()
                    return
                }

                if value.translation.width > threshold {
                    complete(.save)
                } else if value.translation.width < -threshold {
                    complete(.skip)
                } else {
                    resetOffset()
                }
            }
    }

    private func resetOffset() {
        if reduceMotion {
            offset = .zero
        } else {
            withAnimation(.spring(response: 0.3, dampingFraction: 0.8)) { offset = .zero }
        }
    }

    private func complete(_ decision: RecipeDecision) {
        if reduceMotion {
            offset = .zero
            onDecision(decision)
        } else {
            withAnimation(.easeOut(duration: 0.18)) { offset.width = decision == .save ? 700 : -700 }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.16) {
                onDecision(decision)
                offset = .zero
            }
        }
    }
}
