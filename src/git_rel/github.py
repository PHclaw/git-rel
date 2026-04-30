"""Fetch release and PR data from GitHub."""
import requests
import os

GITHUB_API = "https://api.github.com"
HEADERS = {
    "Accept": "application/vnd.github.v3+json",
    "User-Agent": "git-rel/0.1.0",
}
TOKEN = os.environ.get("GITHUB_TOKEN")
if TOKEN:
    HEADERS["Authorization"] = f"token {TOKEN}"


def _get(url, params=None):
    r = requests.get(url, headers=HEADERS, params=params)
    r.raise_for_status()
    return r.json()


def fetch_latest_release(repo):
    """Get the most recent release (or latest tag if no release)."""
    url = f"{GITHUB_API}/repos/{repo}/releases/latest"
    try:
        release = _get(url)
        return release, release.get("tag_name", "")
    except Exception:
        # No releases, get most recent tag
        url = f"{GITHUB_API}/repos/{repo}/git/refs/tags"
        tags = _get(url)
        if tags:
            # Most recent tag is first
            tag_ref = tags[0]["ref"]
            tag_name = tag_ref.replace("refs/tags/", "")
            return {"tag_name": tag_name, "name": tag_name, "body": "", "published_at": ""}, tag_name
        return None, ""


def fetch_tag_commit(repo, tag):
    """Get commit SHA for a given tag."""
    try:
        data = _get(f"{GITHUB_API}/repos/{repo}/git/refs/tags/{tag}")
        if "object" in data and data["object"].get("type") == "tag":
            tag_data = _get(data["object"]["url"])
            obj = tag_data.get("object", {})
            return obj.get("sha", "")
        return data.get("object", {}).get("sha", "")
    except Exception:
        return ""


def fetch_commits_between(repo, base_sha, head_sha):
    """Fetch commits between two SHAs."""
    if not base_sha or not head_sha or base_sha == head_sha:
        return []
    try:
        return _get(
            f"{GITHUB_API}/repos/{repo}/compare/{base_sha}...{head_sha}",
            params={"per_page": 100}
        ).get("commits", [])
    except Exception:
        return []


def fetch_prs_since(repo, base_sha="", tag=""):
    """Fetch merged PRs. If base_sha provided, get PRs between SHAs; otherwise get PRs merged since the tag."""
    if base_sha:
        commits = fetch_commits_between(repo, base_sha, "HEAD")
        pr_numbers = set()
        for commit in commits:
            msg = commit["commit"]["message"].lower()
            # Look for "Merge pull request #N"
            if "merge pull request #" in msg:
                import re
                nums = re.findall(r"#(\d+)", msg)
                for n in nums:
                    pr_numbers.add(int(n))
        return list(pr_numbers)
    
    # Fallback: fetch recent merged PRs
    try:
        data = _get(
            f"{GITHUB_API}/repos/{repo}/pulls",
            params={"state": "closed", "sort": "updated", "direction": "desc", "per_page": 50}
        )
        merged = [pr for pr in data if pr.get("merged_at")]
        return [pr["number"] for pr in merged[:30]]
    except Exception:
        return []


def fetch_pr_details(repo, pr_numbers):
    """Fetch details for a list of PR numbers."""
    prs = []
    for num in pr_numbers:
        try:
            pr = _get(f"{GITHUB_API}/repos/{repo}/pulls/{num}")
            labels = [l["name"] for l in pr.get("labels", [])]
            prs.append({
                "number": num,
                "title": pr.get("title", ""),
                "url": pr.get("html_url", ""),
                "labels": labels,
                "merged_at": pr.get("merged_at", ""),
                "user": pr.get("user", {}).get("login", ""),
                "body": pr.get("body", ""),
            })
        except Exception:
            pass
    return prs


def categorize(pr):
    """Categorize a PR by its labels."""
    labels = pr["labels"]
    label_map = {
        "breaking": ["breaking", "breaking-change", "breaking change"],
        "bugfix": ["bug", "bugfix", "fix", "hotfix"],
        "feature": ["feature", "enhancement", "improvement", "perf"],
        "docs": ["docs", "documentation", "readme"],
        "refactor": ["refactor", "refactoring", "cleanup"],
        "test": ["test", "tests", "testing"],
        "i18n": ["i18n", "internationalization", "translation", "locale"],
        "security": ["security", "cve"],
    }
    for cat, keywords in label_map.items():
        for label in labels:
            if any(kw in label.lower() for kw in keywords):
                return cat
    # Heuristic by title
    title = pr["title"].lower()
    if "fix" in title or "bug" in title:
        return "bugfix"
    if "feat" in title or "add" in title or "support" in title:
        return "feature"
    if "doc" in title or "readme" in title or "changelog" in title:
        return "docs"
    if "test" in title:
        return "test"
    return "other"