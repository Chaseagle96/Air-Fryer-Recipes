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
        let save = app.buttons["discover.save"]
        XCTAssertTrue(save.waitForExistence(timeout: 5))
        save.tap()

        app.tabBars.buttons["Saved"].tap()
        XCTAssertTrue(app.navigationBars["Saved"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Crispy Air Fryer Chicken Thighs"].waitForExistence(timeout: 5))
    }

    func testVerticalSwitchAndNotNowAreIndependentActions() {
        let app = XCUIApplication()
        app.launchArguments = ["--ui-testing"]
        app.launch()

        let slowCooker = app.buttons["vertical.slow_cooker"]
        XCTAssertTrue(slowCooker.waitForExistence(timeout: 5))
        slowCooker.tap()
        let notNow = app.buttons["discover.notNow"]
        XCTAssertTrue(notNow.waitForExistence(timeout: 5))
        notNow.tap()
        XCTAssertTrue(app.buttons["discover.save"].exists)
        XCTAssertTrue(app.buttons["discover.undo"].exists)
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
