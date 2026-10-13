# Bundled LCA sample
`lca_tech_disclosures_2025_2026.csv` is synthetic. It holds 1,728 made-up rows in the column layout of the public LCA disclosure files. Case numbers are sequential, wages are generated, and the employers are the fictional Company A to Company O. No row describes a real filing.
The ETL reads this file when no source URL is given or the download fails. Real runs ingest the LCA disclosure files that the US Department of Labor's Office of Foreign Labor Certification publishes. Point `compflow-cli ingest-live-dol --url` at a CSV export of one of those files.
