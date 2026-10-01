import pytest

from signallens.fetch.ssrf import SSRFBlocked, assert_public_url, is_public_ip


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.1.2.3",
        "172.16.0.1",
        "192.168.1.10",
        "169.254.169.254",  # cloud metadata
        "100.64.0.1",  # CGNAT
        "0.0.0.0",
        "0.1.2.3",
        "255.255.255.255",
        "224.0.0.1",  # multicast
        "240.0.0.1",  # reserved
        "::1",
        "::",
        "fe80::1",
        "fe80::1%eth0",
        "fc00::1",
        "fd12:3456::1",  # unique local
        "::ffff:127.0.0.1",  # IPv4-mapped loopback
        "::ffff:10.0.0.1",
        "::ffff:169.254.169.254",
        "64:ff9b::a00:1",  # NAT64 to 10.0.0.1
        "2002:a00:1::",  # 6to4 wrapping 10.0.0.1
        "not-an-ip",
        "",
    ],
)
def test_non_public_addresses(ip):
    assert not is_public_ip(ip)


@pytest.mark.parametrize(
    "ip", ["93.184.216.34", "8.8.8.8", "1.1.1.1", "2606:4700:4700::1111", "[2001:4860:4860::8888]"]
)
def test_public_addresses(ip):
    assert is_public_ip(ip)


async def test_public_host_passes(fake_dns):
    await assert_public_url("https://razorpay.com/pricing/")
    assert fake_dns.lookups == ["razorpay.com"]


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://10.0.0.5:8080/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "http://2130706433/",  # decimal 127.0.0.1
        "http://127.1/",
        "http://0x7f.0.0.1/",
    ],
)
async def test_ip_literals_are_blocked_without_dns(url, fake_dns):
    with pytest.raises(SSRFBlocked):
        await assert_public_url(url)
    assert fake_dns.lookups == []


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://LOCALHOST:5432/",
        "http://api.localhost/",
        "http://printer.local/",
        "http://metadata.google.internal/",
    ],
)
async def test_internal_hostnames_are_blocked(url, fake_dns):
    with pytest.raises(SSRFBlocked, match="internal"):
        await assert_public_url(url)
    assert fake_dns.lookups == []


async def test_hostname_resolving_to_private_ip_is_blocked(fake_dns):
    fake_dns.records["evil.example.com"] = ["10.0.0.7"]
    with pytest.raises(SSRFBlocked, match="10.0.0.7"):
        await assert_public_url("https://evil.example.com/")


async def test_any_private_address_among_several_blocks(fake_dns):
    fake_dns.records["mixed.example.com"] = ["93.184.216.34", "169.254.169.254"]
    with pytest.raises(SSRFBlocked):
        await assert_public_url("https://mixed.example.com/")


async def test_ipv6_private_resolution_is_blocked(fake_dns):
    fake_dns.records["v6.example.com"] = ["fd00::1"]
    with pytest.raises(SSRFBlocked):
        await assert_public_url("https://v6.example.com/")


@pytest.mark.parametrize(
    "url",
    ["ftp://example.com/file", "file:///etc/passwd", "gopher://x/", "javascript:alert(1)", "example.com/x"],
)
async def test_only_http_and_https(url, fake_dns):
    with pytest.raises(SSRFBlocked, match="scheme"):
        await assert_public_url(url)


@pytest.mark.parametrize(
    "url", ["https://user:pass@example.com/", "https://user@example.com/", "http://example.com@127.0.0.1/"]
)
async def test_credentials_in_url_are_blocked(url, fake_dns):
    with pytest.raises(SSRFBlocked, match="credentials"):
        await assert_public_url(url)


async def test_dns_failure_propagates_as_oserror(fake_dns):
    fake_dns.records["nx.example.com"] = []
    with pytest.raises(OSError):
        await assert_public_url("https://nx.example.com/")


async def test_allow_private_skips_host_and_address_checks(fake_dns):
    await assert_public_url("http://localhost:8000/", allow_private=True)
    await assert_public_url("http://10.0.0.1/", allow_private=True)
    assert fake_dns.lookups == []
    with pytest.raises(SSRFBlocked):
        await assert_public_url("ftp://localhost/", allow_private=True)
