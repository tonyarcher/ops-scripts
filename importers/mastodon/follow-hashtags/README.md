# follow-hashtags

Bulk-follow Mastodon hashtags from a text file, another account's followed_tags, and/or trending tags. Default is dry-run; pass `--apply` to actually POST.

## Sources

- `--file` — a text file with one hashtag per line (`#` optional, comments start with `//`, `;`, or `# `).
- `--source-instance` — copy the followed_tags of the account on another instance (needs `--source-token`).
- `--trends N` — the top N trending tags on `--instance`.

Sources are merged and deduped. Progress is stored in a SQLite state file so re-runs skip tags already followed.

## Flags

| Flag | Default | Description |
| --- | --- | --- |
| `--instance <url>` | env `MASTODON_INSTANCE` | Target instance |
| `--token <token>` | env `MASTODON_ACCESS_TOKEN` | Target token |
| `--file <path>` | — | Tag list file |
| `--source-instance <url>` | env `MASTODON_SOURCE_INSTANCE` | Instance to copy follows from |
| `--source-token <token>` | env `MASTODON_SOURCE_TOKEN` | Token for the source instance |
| `--trends <n>` | — | Follow top n trending tags |
| `--delay-ms <ms>` | 1500 | Min delay between requests |
| `--max <n>` | — | Only follow the first n new tags |
| `--apply` | false | Actually POST follows |
| `--state <path>` | `tmp/follow-hashtags.db` | SQLite state file |
| `--retry-failed` | false | Retry tags previously marked error |
| `--batch-size <n>` | 25 | Log a batch line every n tags |
| `--help` | — | Show usage |

## Scopes

- Target token: `write:follows`.
- Source token (for `--source-instance`): `read:follows`.

## Examples

```
python follow_hashtags.py --file sample-tags.txt
python follow_hashtags.py --instance https://example.social --file sample-tags.txt --apply
python follow_hashtags.py --instance https://new.social --source-instance https://old.social --apply
python follow_hashtags.py --instance https://example.social --trends 20
python -m unittest discover -s tests -v
```

Uses stdlib `urllib` and `sqlite3`. No Bun or Node required.

## Notes

- Following a hashtag affects the account's home timeline — it is not a server-wide import.
- Default is dry-run; nothing is POSTed unless `--apply` is passed.
- State lives in `tmp/follow-hashtags.db` (relative to cwd). Delete it to start over.
- Never commit tokens; read them from the environment.