#!/usr/bin/env python3
"""
Updates README.md with:
- Badges: join year, public repos, gists
- Commit counts (today / this week)
- PR counts (today / this week)
- Recent activity feed (latest public GitHub events)

Requires GITHUB_TOKEN and GITHUB_USERNAME environment variables.
"""

import os
import re
import sys
import datetime
import requests

USERNAME = os.environ.get("GITHUB_USERNAME", "brisolarag")
TOKEN = os.environ["GITHUB_TOKEN"]
README_PATH = os.environ.get("README_PATH", "README.md")

API = "https://api.github.com"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


def gh_get(url, params=None):
    r = requests.get(url, headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def get_profile():
    return gh_get(f"{API}/users/{USERNAME}")


def date_bounds():
    now = datetime.datetime.now(datetime.timezone.utc)
    start_of_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_week = start_of_today - datetime.timedelta(days=now.weekday())  # Monday
    return start_of_today, start_of_week


def search_count(query):
    data = gh_get(f"{API}/search/issues", params={"q": query, "per_page": 1})
    return data.get("total_count", 0)


def count_prs(start_of_today, start_of_week):
    today_iso = start_of_today.strftime("%Y-%m-%dT%H:%M:%S")
    week_iso = start_of_week.strftime("%Y-%m-%dT%H:%M:%S")
    prs_today = search_count(f"author:{USERNAME} type:pr created:>={today_iso}")
    prs_week = search_count(f"author:{USERNAME} type:pr created:>={week_iso}")
    return prs_today, prs_week


def count_commits(start_of_today, start_of_week):
    # Usa a Search API de commits (precisa do Accept header específico)
    headers = dict(HEADERS)
    headers["Accept"] = "application/vnd.github.cloak-preview+json"

    def commit_count(since_dt):
        since_iso = since_dt.strftime("%Y-%m-%dT%H:%M:%S")
        r = requests.get(
            f"{API}/search/commits",
            headers=headers,
            params={"q": f"author:{USERNAME} committer-date:>={since_iso}", "per_page": 1},
            timeout=30,
        )
        r.raise_for_status()
        return r.json().get("total_count", 0)

    return commit_count(start_of_today), commit_count(start_of_week)


EVENT_DESCRIPTIONS = {
    "PushEvent": lambda p: f"Pushed {p.get('size', 1)} commit(s) to {p['repo_name']}",
    "PullRequestEvent": lambda p: f"{p['action'].capitalize()} a pull request in {p['repo_name']}",
    "IssuesEvent": lambda p: f"{p['action'].capitalize()} an issue in {p['repo_name']}",
    "IssueCommentEvent": lambda p: f"Commented on an issue in {p['repo_name']}",
    "CreateEvent": lambda p: f"Created {p.get('ref_type', 'a ref')} in {p['repo_name']}",
    "DeleteEvent": lambda p: f"Deleted {p.get('ref_type', 'a ref')} in {p['repo_name']}",
    "ForkEvent": lambda p: f"Forked {p['repo_name']}",
    "WatchEvent": lambda p: f"Starred {p['repo_name']}",
    "ReleaseEvent": lambda p: f"Published a release in {p['repo_name']}",
    "PublicEvent": lambda p: f"Made {p['repo_name']} public",
}


def get_recent_activity(max_events=1):
    events = gh_get(f"{API}/users/{USERNAME}/events/public", params={"per_page": max_events})
    lines = []
    for event in events[:max_events]:
        event_type = event.get("type")
        repo_name = event.get("repo", {}).get("name", "")
        payload = dict(event.get("payload", {}))
        payload["repo_name"] = repo_name
        describe = EVENT_DESCRIPTIONS.get(event_type)
        created_at_raw = event.get("created_at", "")
        try:
            dt = datetime.datetime.strptime(created_at_raw, "%Y-%m-%dT%H:%M:%SZ")
            timestamp = dt.strftime("%Y-%m-%d %H:%M UTC")
        except ValueError:
            timestamp = created_at_raw
        if describe:
            try:
                lines.append(f"{describe(payload)} ({timestamp})")
            except Exception:
                lines.append(f"{event_type} in {repo_name} ({timestamp})")
        else:
            lines.append(f"{event_type} in {repo_name} ({timestamp})")
    return lines


def render_activity_feed(lines):
    if not lines:
        return "```text\nNo recent public activity.\n```"
    return "```text\n" + lines[0] + "\n```"


def replace_section(content, section_name, new_body):
    pattern = re.compile(
        rf"(<!--START_SECTION:{section_name}-->)(.*?)(<!--END_SECTION:{section_name}-->)",
        re.DOTALL,
    )
    replacement = rf"\1\n{new_body}\n\3"
    if not pattern.search(content):
        print(f"Warning: marker '{section_name}' not found in README.")
        return content
    return pattern.sub(replacement, content)


def replace_badge(content, label, value):
    # Update shields.io badges in the format: label-VALUE-color
    pattern = re.compile(rf"(!\[{re.escape(label)}\]\(https://img\.shields\.io/badge/[^\-]+-)([^\-\)]+)(-)")
    return pattern.sub(lambda m: f"{m.group(1)}{value}{m.group(3)}", content)


def main():
    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    profile = get_profile()
    start_of_today, start_of_week = date_bounds()

    commits_today, commits_week = count_commits(start_of_today, start_of_week)
    prs_today, prs_week = count_prs(start_of_today, start_of_week)
    activity_lines = get_recent_activity()

    # Commits/PRs table
    activity_body = (
        "| Metric | Today | This week |\n"
        "|---|---|---|\n"
        f"| Commits | {commits_today} | {commits_week} |\n"
        f"| Pull requests | {prs_today} | {prs_week} |"
    )
    content = replace_section(content, "activity", activity_body)

    # Last updated timestamp
    now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    content = replace_section(content, "last_updated", f"_Last updated: {now_str}_")

    # Recent activity feed (replaces the old waka section)
    content = replace_section(content, "waka", render_activity_feed(activity_lines))

    # Badges
    joined_year = profile["created_at"][:4]
    content = replace_badge(content, "Joined", joined_year)
    content = replace_badge(content, "Public Repos", str(profile.get("public_repos", 0)))
    content = replace_badge(content, "Gists", str(profile.get("public_gists", 0)))

    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(content)

    print("README atualizado com sucesso.")


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as e:
        print(f"GitHub API error: {e}", file=sys.stderr)
        sys.exit(1)