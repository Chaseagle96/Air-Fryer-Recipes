import XCTest

final class RecipeIntelligenceUITests: XCTestCase {
    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    func testSaveRecipeAppearsInSavedCollection() {
        let app = XCUIApplication()
        app.launchArguments = ["--ui-testing"]
        app.launch()

        XCTAssertTrue(app.navigationBars["Discover"].waitForExistence(timeout: 8))
        let card = app.descendants(matching: .any)["discover.card"]
        XCTAssertTrue(card.waitForExistence(timeout: 5))
        card.swipeRight()

        let undo = app.buttons["discover.undo"]
        XCTAssertTrue(undo.waitForExistence(timeout: 5), "A completed save swipe should expose Undo.")

        app.tabBars.buttons["Saved"].tap()
        XCTAssertTrue(app.navigationBars["Saved"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Crispy Air Fryer Chicken Thighs"].waitForExistence(timeout: 5))
    }

    func testVerticalSwitchAndSwipeSkipAreIndependentActions() {
        let app = XCUIApplication()
        app.launchArguments = ["--ui-testing"]
        app.launch()

        let slowCooker = app.buttons["vertical.slow_cooker"]
        XCTAssertTrue(slowCooker.waitForExistence(timeout: 5))
        slowCooker.tap()

        let card = app.descendants(matching: .any)["discover.card"]
        XCTAssertTrue(card.waitForExistence(timeout: 5))
        let beforeLabel = card.label
        card.swipeLeft()

        let undo = app.buttons["discover.undo"]
        XCTAssertTrue(undo.waitForExistence(timeout: 5), "A completed skip swipe should expose Undo.")

        let nextCard = app.descendants(matching: .any)["discover.card"]
        XCTAssertTrue(nextCard.waitForExistence(timeout: 5))
        XCTAssertNotEqual(nextCard.label, beforeLabel)
    }

    func testAccessibleManualRefreshReportsCurrentFeed() {
        let app = XCUIApplication()
        app.launchArguments = ["--ui-testing"]
        app.launch()

        XCTAssertTrue(app.navigationBars["Discover"].waitForExistence(timeout: 8))
        let refresh = app.buttons["discover.refresh"]
        XCTAssertTrue(refresh.waitForExistence(timeout: 5))
        refresh.tap()
        XCTAssertTrue(app.staticTexts["Recipe Intelligence is up to date."].waitForExistence(timeout: 5))
    }
}
