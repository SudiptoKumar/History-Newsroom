from image_resolver import _image_url_from_html


def test_extract_og_image_absolute():
    html = '<meta property="og:image" content="https://example.com/photo.jpg">'
    assert _image_url_from_html("https://example.com/story", html) == "https://example.com/photo.jpg"


def test_extract_og_image_relative():
    html = '<meta property="og:image" content="/media/photo.jpg">'
    assert _image_url_from_html("https://example.com/story", html) == "https://example.com/media/photo.jpg"
