import SwiftUI

struct RootView: View {
    @EnvironmentObject private var appModel: AppModel

    var body: some View {
        TabView {
            NavigationStack { DiscoverView() }
                .tabItem { Label("Discover", systemImage: "sparkles") }
                .accessibilityIdentifier("tab.discover")

            NavigationStack { SavedView() }
                .tabItem { Label("Saved", systemImage: "heart.fill") }
                .accessibilityIdentifier("tab.saved")

            NavigationStack { PlannerView() }
                .tabItem { Label("Plan", systemImage: "calendar") }
                .accessibilityIdentifier("tab.plan")

            NavigationStack { ShoppingView() }
                .tabItem { Label("Shopping", systemImage: "cart") }
                .accessibilityIdentifier("tab.shopping")

            NavigationStack { ProfileView() }
                .tabItem { Label("Taste", systemImage: "person.2") }
                .accessibilityIdentifier("tab.taste")
        }
        .task { await appModel.bootstrap() }
    }
}
