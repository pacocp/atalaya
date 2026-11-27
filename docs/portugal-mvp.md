# Portugal adaptation: initial implementation

This fork is being adapted incrementally. The original Spanish adapters remain in the repository but are disabled in the active Portuguese registry.

## Active sources

The active registry includes only the Portuguese Diário da República, FCT and Universidade de Lisboa sources, plus EU Funding & Tenders (ERC/MSCA). Spanish adapters remain in code but are not run by the Portuguese edition. Historical records from inactive source keys are excluded from the generated site.

## Implemented

- Diário da República: registered a first-pass scraper for the official RSS index of the 2nd series (all parts, HTML). The parser supports RSS and Atom entries, filters likely recruitment/research notices by title and preserves the original notice URL. Its live response and classification quality still need validation in GitHub Actions; verify each notice and deadline at source.
- Universidade de Lisboa: agregador oficial de recrutamento, com filtro para concursos docentes, investigação e bolsas, extraindo categoria, número de vagas e prazo limite quando publicados. As entradas expiradas são omitidas e o documento principal é preservado em metadados.
- Universidade do Porto: arquivo oficial de oportunidades com filtro `prazo=abertas`; conserva bolsas e recrutamento com sinais explícitos de docência ou investigação, eliminando formação e funções operacionais não académicas.
- Universidade de Coimbra (UC Apply): procedimentos em aberto de Bolsas de Investigação, Docentes, Investigadores e Investigadores DL 57; a extração de prazo e área é complementada pelas páginas públicas de cada procedimento.
- FCT: registered a parser for the official open-concursos tab. It follows same-domain detail pages (up to 40 per run), extracts full deadlines only when linked to submission/closing labels, and records funding type and scientific domain only when supported by the title or structured page metadata. Failed detail requests leave the listing record intact. Live source coverage and extraction quality still need runtime validation.
- Portuguese month names are recognised by `academic_offers.dates.first_date`.
- The classifier recognises a first set of Portuguese academic/research role labels, including professor catedrático, professor associado, professor auxiliar, investigador principal/auxiliar, pós-doutoramento and doutoramento.
- Regression tests cover Portuguese month names and the numeric date format commonly used in Portugal.

## Source research and constraints

### Diário da República

The Diário da República is publicly accessible and provides its first and second series in open electronic formats. Its official help and legal notices describe the public access and reuse framework:

- https://diariodarepublica.pt/dr/geral/ajuda
- https://diariodarepublica.pt/dr/geral/avisos-legais

The official RSS subscription page publishes a link for the second series, all parts, in HTML format: https://files.diariodarepublica.pt/rss/serie2-html.xml. The feed URL is grounded in the publisher's own page, although the web preview used during development could not inspect the XML because it does not support the feed content type. The parser is registered, but its response format and results still need to be validated by the repository's runtime. Do not guess internal website APIs.

### Fundação para a Ciência e a Tecnologia (FCT)

The FCT publishes a public [Concursos](https://www.fct.pt/concursos/) index with open, planned and closed calls, plus filters for funding type and scientific domain. The filter vocabulary includes Bolsas, Emprego científico, Projetos I&D, Instituições I&D, Infraestruturas, Prémios, Internacional and Outros, alongside seven scientific domains. Its [Bolsas](https://www.fct.pt/financiamento/programas-de-financiamento/bolsas/) and [Emprego Científico](https://www.fct.pt/financiamento/programas-de-financiamento/emprego-cientifico/) pages describe major research-opportunity categories. The 2026 calendar is a planning document, not a live vacancy feed. The scraper consumes the open listing at https://www.fct.pt/concursos/?paged=1&tab=open and follows same-domain detail pages, using explicit closing/submission labels for full dates and structured label/value fields for scientific domains. Funding type is taken from the title or an explicit category field. Missing metadata stays missing; the original notice remains authoritative. Live source coverage and extraction quality still need runtime validation. Do not scrape myFCT as a substitute: it is a separate application portal and may expose application-management records rather than the public notice index.

### Universidade de Coimbra — UC Apply

O [UC Apply](https://www.apply.uc.pt/) é o portal oficial da Universidade de Coimbra para publicitar procedimentos concursais de docentes, não docentes e investigadores. A edição portuguesa consulta a pesquisa pública de candidaturas abertas e limita-se a bolsas de investigação, docentes, investigadores e Investigadores DL 57. O detalhe do procedimento pode indicar código, número de postos, área e intervalo de candidaturas. Corpo técnico, dirigentes e bolsas de estágio curricular ficam fora do filtro inicial.

### Universidade do Porto

O [Arquivo de Oportunidades](https://noticias.up.pt/oportunidades/) da U.Porto permite filtrar oportunidades com prazo a decorrer e distinguir categorias como Recrutamento e Bolsas. O parser usa o filtro oficial de prazos abertos e conserva apenas anúncios com sinais explícitos de docência, investigação ou bolsas de investigação; exclui formação e funções operacionais sem relação académica. Só usa datas completas publicadas no cartão e deixa o prazo vazio quando não é apresentado.

### Universidade de Lisboa

A página oficial de [Recrutamento](https://www.ulisboa.pt/info/recrutamento) agrupa oportunidades das escolas e serviços, com código, designação, número de vagas, categoria, data limite e documento principal. A fonte inclui funções administrativas além de vagas académicas; o parser só conserva títulos/categorias com sinais explícitos de docência, investigação, carreiras científicas ou bolsas. Prazo passado é filtrado em tempo de recolha.

### Bolsa de Emprego Público (BEP)

An experimental parser exists at `academic_offers/sources/portugal.py`, but it is intentionally **not registered in SOURCES**. Public search indexing confirms that BEP detail pages contain useful fields such as offer code, career, employer and job description. However, automated access to some detail pages returns a permission-denied response. Do not work around access controls. Validate the public listing/feed with BEP or request an official data feed before enabling this source.

## Important implementation rules

- Do not infer a deadline from a publication date. Extract an explicit closing date or an explicit duration and mark calculated dates as estimates.
- Do not apply Spain's regional holiday calendar or Spanish administrative deadline assumptions to Portugal.
- Preserve the original notice URL and the exact wording of the institution and role.
- A failed source must not erase previously collected offers.
- Honour robots.txt, published crawl delays and source terms; use a descriptive User-Agent and a low request frequency.

## GitHub Pages: one-time repository setup

The scrape, database update and static-site build run successfully in GitHub Actions. The deployment step cannot create the Pages site with the workflow's default `GITHUB_TOKEN`: GitHub requires an administrator-capable token to create the site. Enable it once in the repository settings:

1. Open **Settings → Pages**.
2. Under **Build and deployment**, set **Source** to **GitHub Actions**.
3. Save the setting. The next daily workflow run can then publish the generated `site/` directory.

Do not add a personal access token to the repository just for this unless you deliberately want automated repository administration. A one-time settings change is safer. GitHub documents Pages availability on public repositories with GitHub Free and the Actions publishing source: https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site.

## Next milestones

1. Validate the DR RSS and FCT parsers against live responses in GitHub Actions; measure false positives and pagination coverage.
2. Validate the FCT detail-page extractor against live notices and refine category/domain mappings only when the official page exposes unambiguous metadata.
3. Add explicit Portuguese deadline rules only after checking the relevant notice wording and applicable legal rules.
4. Validate BEP automated access or obtain an authorised feed.
5. Add more Portuguese university and polytechnic career pages with source-specific tests.
