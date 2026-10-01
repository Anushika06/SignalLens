import pytest

from signallens.util.urls import domain_matches, host_of, normalize_url, publisher_key, registrable_domain


class TestNormalizeUrl:
    def test_lowercases_scheme_and_host_and_keeps_path_case(self):
        assert normalize_url("HTTPS://Razorpay.COM/Pricing/") == "https://razorpay.com/Pricing/"

    def test_drops_fragment_and_default_ports(self):
        assert normalize_url("https://razorpay.com:443/pricing/#fees") == "https://razorpay.com/pricing/"
        assert normalize_url("http://example.com:80/a") == "http://example.com/a"

    def test_keeps_non_default_port(self):
        assert normalize_url("https://example.com:8443/a") == "https://example.com:8443/a"

    def test_drops_tracking_params_and_sorts_the_rest(self):
        url = "https://example.com/a?utm_source=x&b=2&UTM_Medium=y&gclid=1&a=1&fbclid=2&mc_cid=3&mc_eid=4&ref_src=5&igshid=6"
        assert normalize_url(url) == "https://example.com/a?a=1&b=2"

    def test_sort_is_stable_for_repeated_params_and_preserves_encoding(self):
        assert normalize_url("https://e.com/s?q=a%20b&tag=z&tag=a") == "https://e.com/s?q=a%20b&tag=z&tag=a"

    def test_empty_path_becomes_slash(self):
        assert normalize_url("https://example.com") == "https://example.com/"
        assert normalize_url("https://example.com?utm_source=x") == "https://example.com/"

    def test_ipv6_host(self):
        assert normalize_url("http://[::1]:8080/a?gclid=1") == "http://[::1]:8080/a"

    def test_equivalent_links_normalise_identically(self):
        a = normalize_url("https://www.example.com/news/story?utm_campaign=x#top")
        b = normalize_url("HTTPS://WWW.EXAMPLE.COM:443/news/story")
        assert a == b


class TestHosts:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("https://WWW.Razorpay.com:8443/x", "www.razorpay.com"),
            ("razorpay.com/pricing", "razorpay.com"),
            ("razorpay.com", "razorpay.com"),
            ("[::1]:80", "::1"),
            ("https://example.com./a", "example.com"),
            ("", ""),
        ],
    )
    def test_host_of(self, value, expected):
        assert host_of(value) == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("https://economictimes.indiatimes.com/x", "indiatimes.com"),
            ("www.rbi.org.in", "rbi.org.in"),
            ("https://www.bbc.co.uk/news", "bbc.co.uk"),
            ("http://10.0.0.1/x", "10.0.0.1"),
            ("localhost", "localhost"),
            ("https://alice.github.io/blog", "alice.github.io"),  # PSL private suffix honoured
        ],
    )
    def test_registrable_domain(self, value, expected):
        assert registrable_domain(value) == expected

    def test_publisher_key_groups_subdomains_of_one_publisher(self):
        assert publisher_key("https://economictimes.indiatimes.com/a") == publisher_key(
            "https://timesofindia.indiatimes.com/b"
        )
        assert publisher_key("https://alice.github.io/") != publisher_key("https://bob.github.io/")


class TestDomainMatches:
    @pytest.mark.parametrize("domain", ["razorpay.com", "https://razorpay.com", "www.razorpay.com"])
    def test_accepts_any_domain_spelling(self, domain):
        assert domain_matches("https://razorpay.com/pricing", [domain])
        assert domain_matches("https://blog.razorpay.com/post", [domain])
        assert domain_matches("https://www.razorpay.com/", [domain])

    def test_rejects_lookalikes(self):
        assert not domain_matches("https://notrazorpay.com/", ["razorpay.com"])
        assert not domain_matches("https://razorpay.com.evil.io/", ["razorpay.com"])

    def test_empty_inputs(self):
        assert not domain_matches("https://razorpay.com/", [])
        assert not domain_matches("", ["razorpay.com"])
        assert not domain_matches("https://razorpay.com/", [""])
