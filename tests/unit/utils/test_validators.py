from app.utils.validators import is_safe_path, is_valid_filename, is_valid_url, validate_duration_seconds


def test_is_valid_filename_allows_safe_characters():
    assert is_valid_filename("video_name.mp4")
    assert not is_valid_filename("../secret")


def test_is_valid_url_accepts_http_and_https():
    assert is_valid_url("https://www.example.com")
    assert is_valid_url("http://localhost/resource")
    assert not is_valid_url("ftp://example.com")


def test_is_safe_path_rejects_parent_navigation():
    assert not is_safe_path("../video.mp4")
    assert is_safe_path("assets/video.mp4")


def test_validate_duration_seconds_bounds():
    assert validate_duration_seconds(60)
    assert not validate_duration_seconds(0)
    assert not validate_duration_seconds(86401)
