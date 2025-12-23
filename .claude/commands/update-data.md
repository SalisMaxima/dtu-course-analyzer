Run the DTU Course Analyzer data pipeline to update course data.

## Steps

1. First, check if `secret.txt` exists and warn if it might be stale (> 24 hours old)
2. If auth needed, run `dtu-auth` (requires DTU_USERNAME and DTU_PASSWORD env vars)
3. Run `dtu-get-courses` to update course list (coursenumbers.txt)
4. Run `dtu-scrape` to fetch grades and reviews from kurser.dtu.dk
5. Run `dtu-validate coursedic.json` to validate data integrity
6. Run `dtu-analyze extension` to generate `extension/db/data.js`
7. Report summary: courses processed, any errors encountered

## CLI Commands (in order)

```bash
# Set credentials if not already set
export DTU_USERNAME='username'
export DTU_PASSWORD='password'

# Full pipeline
dtu-auth                      # Playwright login, saves secret.txt
dtu-get-courses               # Fetch course list
dtu-scrape                    # Async scraper (MAX_CONCURRENT=2)
dtu-validate coursedic.json   # Validate before analysis
dtu-analyze extension         # Generate data.js and db.html
```

## Notes

- The scraper requires a valid ASP.NET_SessionId cookie in `secret.txt`
- Scraping 1,418 courses takes ~30-45 minutes at MAX_CONCURRENT=2
- If scraper gets timeouts, do NOT increase concurrency — it makes it worse
- If auth fails with 403/401, re-run `dtu-auth`
- Always validate before analyze to catch data issues early
