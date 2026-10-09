// Background service worker for Shan Shui Scroll
if (typeof browser !== "undefined" && browser.action && browser.action.onClicked) {
  browser.action.onClicked.addListener(() => {
    browser.tabs.create({ url: "index.html" });
  });
}
