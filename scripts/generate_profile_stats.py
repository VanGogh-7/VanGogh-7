#!/usr/bin/env python3
"""Generate light and dark SVG cards from VanGogh-7's public GitHub data."""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any

API_ROOT = "https://api.github.com"
GRAPHQL_URL = "https://api.github.com/graphql"
USERNAME = "VanGogh-7"
USER_AGENT = "VanGogh-7-profile-assets"


def api_request(url: str, token: str | None, payload: dict[str, Any] | None = None) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"GitHub API request failed with HTTP {error.code}: {detail}") from error


def public_repositories(token: str | None) -> list[dict[str, Any]]:
    repositories: list[dict[str, Any]] = []
    page = 1
    while True:
        batch = api_request(
            f"{API_ROOT}/users/{USERNAME}/repos?type=owner&sort=updated&per_page=100&page={page}",
            token,
        )
        repositories.extend(batch)
        if len(batch) < 100:
            return repositories
        page += 1


def language_footprint(repositories: list[dict[str, Any]], token: str | None) -> Counter[str]:
    totals: Counter[str] = Counter()
    for repository in repositories:
        if repository.get("fork"):
            continue
        languages = api_request(repository["languages_url"], token)
        totals.update({name: int(byte_count) for name, byte_count in languages.items()})
    return totals


def contribution_count(token: str | None) -> tuple[int, datetime, datetime] | None:
    if not token:
        return None

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=365)
    query = """
      query($login: String!, $from: DateTime!, $to: DateTime!) {
        user(login: $login) {
          contributionsCollection(from: $from, to: $to) {
            contributionCalendar { totalContributions }
          }
        }
      }
    """
    result = api_request(
        GRAPHQL_URL,
        token,
        {
            "query": query,
            "variables": {
                "login": USERNAME,
                "from": start.isoformat(),
                "to": end.isoformat(),
            },
        },
    )
    if result.get("errors"):
        raise RuntimeError(f"GitHub GraphQL query failed: {result['errors']}")
    total = result["data"]["user"]["contributionsCollection"]["contributionCalendar"][
        "totalContributions"
    ]
    return int(total), start, end


def metric_block(x: int, value: int, label: str, colors: dict[str, str]) -> str:
    return f"""
      <rect x="{x}" y="92" width="270" height="84" rx="10" fill="{colors['surface_alt']}" stroke="{colors['border']}"/>
      <text x="{x + 20}" y="132" class="metric">{value:,}</text>
      <text x="{x + 20}" y="157" class="label">{escape(label)}</text>"""


def render_svg(
    theme: str,
    public_repo_count: int,
    followers: int,
    contributions: tuple[int, datetime, datetime] | None,
    languages: Counter[str],
) -> str:
    palettes = {
        "dark": {
            "background": "#0d1117",
            "surface": "#161b22",
            "surface_alt": "#101720",
            "primary": "#58a6ff",
            "cyan": "#39c5cf",
            "violet": "#a371f7",
            "muted": "#8b949e",
            "text": "#f0f6fc",
            "border": "#30363d",
            "track": "#21262d",
        },
        "light": {
            "background": "#ffffff",
            "surface": "#f6f8fa",
            "surface_alt": "#f0f4f8",
            "primary": "#0969da",
            "cyan": "#16858c",
            "violet": "#8250df",
            "muted": "#57606a",
            "text": "#1f2328",
            "border": "#d0d7de",
            "track": "#d8dee4",
        },
    }
    colors = palettes[theme]
    metrics: list[tuple[int, str]] = []
    period = "PUBLIC GITHUB DATA"
    if contributions:
        metrics.append((contributions[0], "CONTRIBUTIONS / 365 DAYS"))
        period = f"PUBLIC ACTIVITY · {contributions[1]:%d %b %Y} — {contributions[2]:%d %b %Y}"
    metrics.extend([(public_repo_count, "PUBLIC REPOSITORIES"), (followers, "FOLLOWERS")])

    positions = [65, 365, 665] if len(metrics) == 3 else [215, 515]
    metric_markup = "".join(
        metric_block(x, value, label, colors) for x, (value, label) in zip(positions, metrics)
    )

    top_languages = languages.most_common(5)
    max_bytes = top_languages[0][1] if top_languages else 1
    total_bytes = sum(languages.values()) or 1
    accents = [colors["primary"], colors["violet"], colors["cyan"], "#d29922", "#7ee787"]
    language_rows = []
    for index, (language, byte_count) in enumerate(top_languages):
        y = 247 + index * 27
        width = max(4, round(470 * byte_count / max_bytes))
        percentage = 100 * byte_count / total_bytes
        language_rows.append(
            f"""
      <text x="66" y="{y + 6}" class="language">{escape(language)}</text>
      <rect x="215" y="{y - 8}" width="470" height="12" rx="6" fill="{colors['track']}"/>
      <rect x="215" y="{y - 8}" width="{width}" height="12" rx="6" fill="{accents[index]}"/>
      <text x="706" y="{y + 5}" class="percentage">{percentage:.1f}%</text>"""
        )

    generated = datetime.now(timezone.utc).strftime("%d %b %Y UTC")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="410" viewBox="0 0 1000 410" role="img" aria-labelledby="title description">
  <title id="title">VanGogh-7 public GitHub activity</title>
  <desc id="description">Public contribution, repository, follower, and repository-language statistics generated from the GitHub API.</desc>
  <style>
    .sans {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }}
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }}
    .eyebrow {{ font: 600 12px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; letter-spacing: 2px; fill: {colors['primary']}; }}
    .heading {{ font: 600 21px -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; fill: {colors['text']}; }}
    .period {{ font: 500 11px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {colors['muted']}; }}
    .metric {{ font: 600 27px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {colors['text']}; }}
    .label {{ font: 600 10px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; letter-spacing: 1px; fill: {colors['muted']}; }}
    .language {{ font: 600 13px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {colors['text']}; }}
    .percentage {{ font: 500 11px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; fill: {colors['muted']}; }}
  </style>
  <rect x="1" y="1" width="998" height="408" rx="14" fill="{colors['background']}" stroke="{colors['border']}" stroke-width="2"/>
  <path d="M1 14A13 13 0 0 1 14 1H986A13 13 0 0 1 999 14V18H1Z" fill="{colors['primary']}" opacity="0.72"/>
  <text x="45" y="49" class="eyebrow">GITHUB / ACTIVITY</text>
  <text x="45" y="74" class="heading">Public profile telemetry</text>
  <text x="955" y="49" text-anchor="end" class="period">{escape(period)}</text>
  {metric_markup}
  <line x1="45" y1="202" x2="955" y2="202" stroke="{colors['border']}"/>
  <text x="45" y="226" class="eyebrow">REPOSITORY-LANGUAGE FOOTPRINT</text>
  {''.join(language_rows)}
  <text x="955" y="386" text-anchor="end" class="period">UPDATED {generated}</text>
</svg>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("dist"))
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    profile = api_request(f"{API_ROOT}/users/{USERNAME}", token)
    repositories = public_repositories(token)
    languages = language_footprint(repositories, token)
    contributions = contribution_count(token)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for theme in ("dark", "light"):
        output = args.output_dir / f"profile-stats-{theme}.svg"
        output.write_text(
            render_svg(
                theme,
                int(profile["public_repos"]),
                int(profile["followers"]),
                contributions,
                languages,
            ),
            encoding="utf-8",
        )
        print(f"generated {output}")


if __name__ == "__main__":
    main()
