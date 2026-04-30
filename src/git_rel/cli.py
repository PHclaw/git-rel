"""CLI entry point for git-rel."""
import argparse
import sys
from datetime import datetime
from .github import fetch_latest_release, fetch_prs_since, fetch_pr_details, fetch_tag_commit, fetch_commits_between
from .changelog import format_changelog


def main():
    parser = argparse.ArgumentParser(
        prog="git-rel",
        description="Generate changelogs from GitHub releases and merged PRs",
    )
    parser.add_argument("repo", help="GitHub repo in owner/name format, e.g. mem0ai/mem0")
    parser.add_argument("--format", "-f", choices=["markdown", "json", "text"], default="markdown",
                        help="Output format (default: markdown)")
    parser.add_argument("--since", "-s", default="",
                        help="Tag to compare from (default: previous release)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show debug info")
    args = parser.parse_args()

    if "/" not in args.repo:
        print("Error: repo must be in owner/name format (e.g. mem0ai/mem0)", file=sys.stderr)
        sys.exit(1)

    try:
        # 1. Get latest release
        release, current_tag = fetch_latest_release(args.repo)
        if not release:
            print(f"No releases or tags found for {args.repo}", file=sys.stderr)
            sys.exit(1)

        tag = args.since or current_tag
        if args.verbose:
            print(f"Current release tag: {current_tag}", file=sys.stderr)
            print(f"Comparing from: {tag}", file=sys.stderr)

        # 2. Get previous tag for comparison
        from .github import _get
        try:
            tags_data = _get(f"https://api.github.com/repos/{args.repo}/git/refs/tags")
            tag_names = []
            for ref in tags_data:
                name = ref["ref"].replace("refs/tags/", "")
                if name != current_tag:
                    tag_names.append(name)
            prev_tag = tag_names[0] if tag_names else ""
        except Exception:
            prev_tag = ""

        # 3. Fetch commits/PRs between tags
        if prev_tag:
            commits = fetch_commits_between(args.repo, prev_tag, current_tag)
            if args.verbose:
                print(f"Found {len(commits)} commits between {prev_tag} and {current_tag}", file=sys.stderr)

            # Extract PR numbers from commit messages
            import re
            pr_numbers = set()
            for commit in commits:
                msg = commit["commit"]["message"]
                nums = re.findall(r"#(\d+)", msg.split("\n")[0])
                pr_numbers.update(int(n) for n in nums)
            pr_numbers = sorted(pr_numbers, reverse=True)
        else:
            # Fallback: fetch recent merged PRs
            pr_numbers = fetch_prs_since(args.repo)
            if args.verbose:
                print(f"Fallback: fetched {len(pr_numbers)} recent PRs", file=sys.stderr)

        # 4. Get PR details
        prs = fetch_pr_details(args.repo, pr_numbers) if pr_numbers else []

        # 5. Categorize
        from .github import categorize as do_categorize
        for pr in prs:
            pr["_cat"] = do_categorize(pr)

        # 6. Format output
        date = release.get("published_at", "")[:10] if release.get("published_at") else datetime.now().strftime("%Y-%m-%d")
        output = format_changelog(prs, tag=current_tag, date=date, format=args.format, repo=args.repo)

        print(output)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()