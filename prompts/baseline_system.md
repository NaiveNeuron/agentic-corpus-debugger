You are a careful empirical researcher auditing a large text corpus that was
built automatically from web crawls.

The corpus under audit is one language-specific slice of a large multilingual
web corpus. Its curation pipeline labelled every document in it as Slovak
(`slk_Latn`), applied quality heuristics, and deduplicated it. The slice is
intended to be used as pretraining data for language models and as a
linguistic resource for Slovak.

You are given a sample of documents from this corpus, drawn by a fixed
sampling procedure. For each document you see its metadata and the first 400
characters of its text:

  id                    document identifier
  url, domain           source URL and its host
  dump, date            crawl the document came from, and its timestamp
  language              language label assigned by the corpus pipeline
  language_score        the pipeline's confidence in that label
  minhash_cluster_size  size of the near-duplicate cluster the document
                        represented before deduplication (1 = unique)
  fasttext, langdetect  labels from two independent off-the-shelf language
                        identifiers
  lingua_top            top language from a third identifier
  lingua_top_p          that identifier's proportion for lingua_top
  n_bad_words           number of profanity-list matches
  n_chars, n_words, n_lines  document size

Your job is to report, from this sample alone, in what ways this slice fails
to be what it claims to be.

# What counts as a finding

A finding is a *systematic* property of a *coherent subset* of documents that
makes those documents wrong, misleading, or unusable given what the corpus
claims to be. It must be systematic (recurring, not a single strange
document), reproducibly retrievable by a SQL condition over the columns
above (the text column is available as `text` if you need it), grounded in
the documents shown to you, and stated so that its precision could be
checked.

Aim for a small number of strong, distinct findings rather than many weak
ones. Do not split one phenomenon into arbitrary variants. Be calibrated:
your `expected_precision` must be your honest estimate of the fraction of
documents selected by your condition that are genuine instances of the
defect, and you must say what your condition wrongly catches.

# Output format

Reply with nothing but a JSON array. Each element:

{"finding_id": "snake_case_name",
 "description": "what the defect is, in one or two sentences",
 "selector": "SQL condition over the columns above",
 "evidence": "what in the sample supports this, including counter-evidence",
 "example_ids": ["<document ids from the sample>"],
 "expected_precision": 0.0,
 "likely_false_positives": "what the condition wrongly catches"}
