# Similar courses

Course pages show up to five courses whose catalogue descriptions are closest
in meaning, with each one's rating and workscore percentiles. The data lives in
`extension/db/similar.json`; until it is generated the file is an empty
placeholder and the section is hidden.

## How it is built

1. `dtu-scrape-details` fetches the English page of every course in
   `extension/db/data.json` and parses *General course objectives*, *Learning
   objectives*, *Content* and *Not applicable together with*. The Danish page
   is fetched only when the English one has no description. Output:
   `data/course_details.json`.
2. `dtu-build-similarity` embeds `"{title}. {objectives} {learning objectives}
   {content}"` with [EmbeddingGemma 2](https://huggingface.co/google/embeddinggemma-2)
   (text encoder only, `SentenceSimilarity` prompt, float32), ranks courses by
   cosine similarity and stores the top 10 per course.

Only neighbour lists are shipped (course number and score), not vectors or
the model, so the extension needs no new permissions.

## Equivalent courses are excluded

Courses linked by *Not applicable together with* are never listed as each
other's neighbours. Every course number in the field counts, including those
inside combinations: for 01001, `(01911.01922)(01901/01910).01920)/01003/`
excludes 01911, 01922, 01901, 01910, 01920 and 01003. A pair is excluded when
either course lists the other, because DTU does not always repeat the
restriction on both pages.

## Updating

Run the **Build Course Similarity** workflow (Actions → workflow_dispatch). It
uploads `similar.json`, `course_details.json` and `report.md`. The report lists
neighbours for well-known courses, near-identical pairs that have no exclusion
link, and courses without description text. When the samples look right,
commit the new `similar.json` to `extension/db/`.

`similar.json` is excluded from the course-data candidate's runtime hash, so
updating it does not invalidate a pending data promotion.

Locally:

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[similarity]"
dtu-auth
dtu-scrape-details
dtu-build-similarity --report similarity-report.md
```
