class SafariMagicExt < Formula
  desc "CLI to explore, install, and create Safari AI Magic Extensions"
  homepage "https://vatsal057.github.io/safari-magic-extensions"
  url "https://github.com/Vatsal057/safari-magic-extensions/archive/refs/tags/v1.1.1.tar.gz"
  sha256 "8ec73d9ba73844f17a6ab4362782835bb8c766b8221e0cf9807401323fa90858"
  license "MIT"
  head "https://github.com/Vatsal057/safari-magic-extensions.git", branch: "main"

  uses_from_macos "python"

  def install
    bin.install "safari-magic-ext.py" => "safari-magic-ext"
  end

  test do
    assert_match "safari-magic-ext #{version}", shell_output("#{bin}/safari-magic-ext --version")
  end
end
