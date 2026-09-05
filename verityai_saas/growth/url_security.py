import http.client
import ipaddress
import re
import socket
import ssl
import time
from dataclasses import dataclass
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit

import frappe


ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443}
BLOCKED_HOST_SUFFIXES = (".internal", ".intranet", ".local", ".localhost", ".test")
MAX_REDIRECTS = 5
MAX_RESPONSE_BYTES = 1024 * 1024
USER_AGENT = "VerityAI-WebsiteDoctor/1.0"
HOST_LABEL_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


@dataclass(frozen=True)
class FetchResult:
	url: str
	status_code: int
	headers: dict
	body: bytes
	resolved_ip: str
	duration_ms: int
	redirect_count: int


def canonical_public_url(value):
	value = str(value or "").strip()
	if not value:
		frappe.throw("Enter a website URL.", frappe.ValidationError)
	if len(value) > 2048 or any(ord(character) < 32 for character in value):
		frappe.throw("Website URL is invalid or too long.", frappe.ValidationError)
	if "://" not in value:
		value = f"https://{value}"
	try:
		parsed = urlsplit(value)
		port = parsed.port
	except ValueError:
		frappe.throw("Website URL contains an invalid port.", frappe.ValidationError)
	if parsed.scheme.lower() not in ALLOWED_SCHEMES or not parsed.hostname or parsed.username or parsed.password:
		frappe.throw("Enter a public HTTP or HTTPS URL without embedded credentials.", frappe.ValidationError)
	if port and port not in ALLOWED_PORTS:
		frappe.throw("Only standard HTTP and HTTPS ports are allowed.", frappe.ValidationError)
	try:
		host = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
	except UnicodeError:
		frappe.throw("Website hostname is invalid.", frappe.ValidationError)
	if not host or host == "localhost" or host.endswith(BLOCKED_HOST_SUFFIXES) or "\\" in parsed.path:
		frappe.throw("Private and local website addresses are not allowed.", frappe.PermissionError)
	try:
		literal_address = ipaddress.ip_address(host)
	except ValueError:
		labels = host.split(".")
		if len(host) > 253 or len(labels) < 2 or any(not HOST_LABEL_PATTERN.fullmatch(label) for label in labels):
			frappe.throw("Website hostname is invalid.", frappe.ValidationError)
	else:
		if not literal_address.is_global:
			frappe.throw("Private, local, reserved and non-public network addresses are not allowed.", frappe.PermissionError)
	try:
		path = quote(unquote(parsed.path or "/"), safe="/%:@!$&'()*+,;=-._~")
	except UnicodeError:
		frappe.throw("Website URL path is invalid.", frappe.ValidationError)
	# Audits intentionally discard query strings so secrets and tracking values are
	# never persisted or copied into unlisted reports.
	netloc = host
	if ":" in host and not host.startswith("["):
		netloc = f"[{host}]"
	if port and port != (443 if parsed.scheme.lower() == "https" else 80):
		netloc = f"{netloc}:{port}"
	return urlunsplit((parsed.scheme.lower(), netloc, path, "", ""))


def resolve_public_addresses(hostname, port, resolver=socket.getaddrinfo):
	try:
		rows = resolver(hostname, port, type=socket.SOCK_STREAM)
	except OSError:
		frappe.throw("The website hostname could not be resolved.", frappe.ValidationError)
	addresses = sorted({row[4][0].split("%", 1)[0] for row in rows})
	if not addresses:
		frappe.throw("The website hostname could not be resolved.", frappe.ValidationError)
	for address in addresses:
		try:
			ip = ipaddress.ip_address(address)
		except ValueError:
			frappe.throw("The website resolved to an invalid network address.", frappe.PermissionError)
		if not ip.is_global:
			frappe.throw("Private, local, reserved and non-public network addresses are not allowed.", frappe.PermissionError)
	return addresses


class _PinnedHTTPConnection(http.client.HTTPConnection):
	def __init__(self, hostname, address, port, timeout):
		super().__init__(hostname, port=port, timeout=timeout)
		self.address = address

	def connect(self):
		self.sock = socket.create_connection((self.address, self.port), self.timeout)


class _PinnedHTTPSConnection(_PinnedHTTPConnection):
	def connect(self):
		raw_socket = socket.create_connection((self.address, self.port), self.timeout)
		self.sock = ssl.create_default_context().wrap_socket(raw_socket, server_hostname=self.host)


def _open_pinned(url, address, timeout):
	parsed = urlsplit(url)
	port = parsed.port or (443 if parsed.scheme == "https" else 80)
	connection_class = _PinnedHTTPSConnection if parsed.scheme == "https" else _PinnedHTTPConnection
	connection = connection_class(parsed.hostname, address, port, timeout)
	path = parsed.path or "/"
	if parsed.query:
		path = f"{path}?{parsed.query}"
	host_header = parsed.hostname
	if ":" in host_header and not host_header.startswith("["):
		host_header = f"[{host_header}]"
	default_port = 443 if parsed.scheme == "https" else 80
	if parsed.port and parsed.port != default_port:
		host_header = f"{host_header}:{parsed.port}"
	connection.request("GET", path, headers={
		"Host": host_header,
		"User-Agent": USER_AGENT,
		"Accept": "text/html,application/xhtml+xml",
		"Accept-Encoding": "identity",
		"Connection": "close",
	})
	return connection, connection.getresponse()


def fetch_public_html(url, resolver=socket.getaddrinfo, opener=_open_pinned, maximum_bytes=MAX_RESPONSE_BYTES, timeout=15):
	current = canonical_public_url(url)
	seen = set()
	started = time.monotonic()
	for redirect_count in range(MAX_REDIRECTS + 1):
		if current in seen:
			frappe.throw("Website redirect loop detected.", frappe.ValidationError)
		seen.add(current)
		parsed = urlsplit(current)
		port = parsed.port or (443 if parsed.scheme == "https" else 80)
		addresses = resolve_public_addresses(parsed.hostname, port, resolver=resolver)
		last_error = None
		for address in addresses:
			connection = None
			try:
				connection, response = opener(current, address, timeout)
				break
			except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
				last_error = exc
				if connection:
					connection.close()
		else:
			raise frappe.ValidationError("The website could not be reached securely.") from last_error
		try:
			headers = {key.lower(): value.strip() for key, value in response.getheaders()}
			if response.status in {301, 302, 303, 307, 308}:
				location = headers.get("location")
				if not location:
					frappe.throw("Website redirect did not include a destination.", frappe.ValidationError)
				next_url = canonical_public_url(urljoin(current, location))
				if parsed.scheme == "https" and urlsplit(next_url).scheme != "https":
					frappe.throw("HTTPS audits cannot follow a downgrade redirect.", frappe.PermissionError)
				current = next_url
				continue
			if response.status < 200 or response.status >= 300:
				frappe.throw(f"Website returned HTTP {response.status}.", frappe.ValidationError)
			content_type = headers.get("content-type", "").split(";", 1)[0].lower()
			if content_type not in {"text/html", "application/xhtml+xml"}:
				frappe.throw("Website did not return an HTML page.", frappe.ValidationError)
			if headers.get("content-encoding", "identity").lower() not in {"", "identity"}:
				frappe.throw("Compressed audit responses are not accepted.", frappe.ValidationError)
			try:
				content_length = int(headers.get("content-length", 0) or 0)
			except ValueError:
				content_length = 0
			if content_length > maximum_bytes:
				frappe.throw("Website response exceeds the audit size limit.", frappe.ValidationError)
			body = response.read(maximum_bytes + 1)
			if len(body) > maximum_bytes:
				frappe.throw("Website response exceeds the audit size limit.", frappe.ValidationError)
			return FetchResult(
				url=current, status_code=response.status, headers=headers, body=body, resolved_ip=address,
				duration_ms=max(round((time.monotonic() - started) * 1000), 1), redirect_count=redirect_count,
			)
		finally:
			connection.close()
	frappe.throw("Website redirected too many times.", frappe.ValidationError)
