# Finding adjudication package

34 candidate findings, clustered mechanically into 11 groups by document-set overlap (Jaccard $\geq$ 0.8, or containment $\geq$ 0.9 between slices of comparable size, for nested selectors). Members of a group retrieve substantially the same documents, so one decision per group is enough; split a group by adding rows for individual finding ids to `decisions.csv` if you disagree.

For each group decide **approve**, **reject** or **unsure** in `decisions.csv`: is this a genuine, coherent, systematic defect of a corpus that claims to be Slovak web text? Which audit strategy produced each candidate is shown, since the grouping already reveals it; ignore it when judging.

## G01: firebase_content_farm_spam

**Members (8).** A large group can mix related but distinct claims; if so, add a row per finding id to `decisions.csv` instead of one row for the group.

* `firebase_content_farm_spam` (agent:main, 1,408,437 docs): A large-scale, machine-generated content-farm/SEO-spam network is hosted on randomly-named subdomains of Google's free Firebase hosting (*.firebaseapp.com, *.web.app). Each subdomain name is a Slovak   
  `domain LIKE '%.firebaseapp.com' OR domain LIKE '%.web.app'`
* `firebase_doorway_spam_farm` (agent:rep1, 1,408,437 docs): A large content-farm/doorway-page spam campaign hosted on randomly-named *.firebaseapp.com and *.web.app subdomains (topic-word + random suffix, e.g. akozbohatnutmulk.firebaseapp.com, danexbnl.firebas  
  `domain LIKE '%.firebaseapp.com' OR domain LIKE '%.web.app'`
* `firebase_webapp_content_farm` (agent:rep2, 1,408,437 docs): A massive programmatic content-farm/doorway-page network hosted on Google Firebase's free static hosting (*.firebaseapp.com and *.web.app subdomains) accounts for over 5% of the entire corpus. Each do  
  `domain LIKE '%.firebaseapp.com' OR domain LIKE '%.web.app'`
* `firebase_webapp_spam_farms` (baseline:lid_disagree, 1,408,437 docs): A large share of documents come from randomly-named subdomains on firebaseapp.com and web.app (often with keyword-stuffed names in Slovak/Czech/Swedish like 'investovat', 'kryptomena', 'valuta', 'prac  
  `language='slk' AND (domain LIKE '%.firebaseapp.com' OR domain LIKE '%.web.app')`
* `programmatic_doorway_spam_pages` (baseline:lowconf, 1,408,437 docs): A large fraction of the sample consists of machine-generated 'doorway' pages on randomly-named Firebase-hosted subdomains (e.g. *.firebaseapp.com, *.web.app, with paths like /NNNNN/NNNNN.html) that sp  
  `domain LIKE '%.firebaseapp.com' OR domain LIKE '%.web.app'`
* `programmatic_seo_farm_boilerplate` (baseline:lowconf, 1,408,437 docs): A large fraction of the slice consists of auto-generated 'content farm' pages hosted on randomly-named firebaseapp.com/web.app subdomains (currency converters, crypto-coin explainers, 'how to get rich  
  `domain LIKE '%.firebaseapp.com' OR domain LIKE '%.web.app'`
* `doorway_spam_domains` (baseline:random, 1,408,437 docs): A recognizable cluster of documents comes from auto-generated 'doorway' pages hosted on random-alphanumeric Firebase/Google App subdomains (*.firebaseapp.com, *.web.app). Their text is not authored pr  
  `domain LIKE '%.firebaseapp.com' OR domain LIKE '%.web.app'`
* `firebase_webapp_doorway_spam` (baseline:random, 1,408,437 docs): A recurring cluster of documents comes from randomly-named subdomains on firebaseapp.com and web.app (Google Firebase free hosting), containing incoherent text stitched from unrelated topic fragments   
  `domain LIKE '%.firebaseapp.com' OR domain LIKE '%.web.app'`

**Description.** A large-scale, machine-generated content-farm/SEO-spam network is hosted on randomly-named subdomains of Google's free Firebase hosting (*.firebaseapp.com, *.web.app). Each subdomain name is a Slovak or Scandinavian finance/get-rich-quick keyword (e.g. "akozbohatnut" = how to get rich, "investerarpengar" = Swedish "invest money", "pracovnemiesta" = job vacancies, "danove" = taxes, "nakupzlata" = buy gold) plus a random letter suffix, and each hosts thousands of pages of incoherent, multi-topic text stitched together from scraped fragments (finance/crypto glossary snippets, news snippets, unrelated Q&A, sometimes switching mid-document into Czech, Bosnian/Serbian, or Slovenian). The pages are not authored prose and are not really "Slovak documents" in the intended sense, despite passing the language filter with high average confidence (0.98) and evading near-duplicate dedup entirely (avg minhash_cluster_size ≈ 1, since every domain/page uses a unique random suffix/URL).

**Selector.** `domain LIKE '%.firebaseapp.com' OR domain LIKE '%.web.app'`

**Prevalence.** 1,408,437 of 26,470,482 (5.3208%), exact on the full corpus.

**Overlap with the obvious static slices.** LID-Disagree 13%, LowConf 3%, HighDup 0%

**Auditor's own precision estimate.** 0.95

**Auditor's stated likely false positives.** A genuine small Slovak personal or hobby site legitimately hosted on Firebase (free Google hosting is popular for small apps/blogs) would be wrongly caught; none were observed in ~32 inspected documents, but the selector cannot distinguish them from the farm by domain pattern alone.

**Fresh examples the auditor never saw:**

* `<urn:uuid:d8d00473-468c-44c0-9d0a-bf7ea4b56911>` <https://investicieaggm.firebaseapp.com/30812/25377.html>

  ```
  13 najlepších bezplatných editorov HTML pre počítače so systémom Tu v tomto príspevku sme uviedli zoznam najlepších editorov HTML pre Atóm Io min.
  Jaskynné maľby, hlinené tabuľky s klinovým písmom, pergameny, knihy, diskety a flash čipy - všetky majú čosi spoločné. Slúžia na ukladanie dát, ktorých hustota sa v priebehu storočí výrazne zvýšila. Akademici z holandskej University of Delft sa pri svojich Tichý šepot atómov má zrýchliť kvantové počítače Technológie 12.09.2014 09:17 Vedcom sa podarilo komunikovať s umelým atómom pomocou zvuku, ktorý tak na seba prebral úlohu svetla. Existujúcim spôsobom dopravy v eshope môžete priradiť, aké spôsoby dopravy sa budú zobrazovať na Heuréke pri tovaroc
  ```

* `<urn:uuid:6307131d-6a46-46ae-8b3f-a20025c04d03>` <https://pracovnemiestatjee.firebaseapp.com/85847/46460.html>

  ```
  Cnnfn svetove trhy europe
  Komoditné trhy v nedávnej dobe preukázali zvýšenú volatilitu a došlo k dovtedy nevídaným zmenám cien. Ceny na všetkých najdôležitejších komoditných trhoch vrátane trhu s energiami, kovmi a minerálmi, poľnohospodárskymi produktmi a potravinami značne narástli v roku 2007 a dosiahli vrchol v roku 2008.
  Tento rok to je 100-ročný a 30 metrov vysoký smrek zo Štajerska, ktorý bude stáť v srdci vianočných trhov. Širší južný Kaukaz je rozhodujúcou tepnou pre plyn a ropu z Azerbajdžanu do Turecka a na európske a ďalšie svetové trhy. Azerbajdžan dodáva asi 5% európskej spotreby plynu a ropy (pomáha znižovať závislosť EÚ od Ruska). Boje v roku 2016 sa priblížili mnohým z týcht
  ```

* `<urn:uuid:350775fa-3117-4095-bf2c-1cf681b38fdf>` <https://megaloadsrprk.web.app/64573/615.html>

  ```
  Ako funguje coinbase reddit
  Coinbase poznamenáva, že zatiaľ čo "rafinérie, ťažiari a dodávateľské reťazce zlata boli narušené, základný protokol Bitcoinu naďalej funguje tak, ako bol navrhnutý" – s tým, že hash rate Bitcoinu sa v posledných týždňoch priblížil k historicky najvyšším hodnotám.
  júna 2017. It seems to me (at this point I feel it is obvious) that Coinbase has been prioritizing adding Ethereum tokens. There are so many other too cryptos such as VeChain 43 votes, 61 comments. Now that they've removed the one thing they had that made them distinct from other exchanges (No fees on maker orders). I … Instead of making thousands, GDAX bull platform lost me my whole account 10k+ . I had
  ```

## G02: czech_slovak_code_switched_docs

**Members (14).** A large group can mix related but distinct claims; if so, add a row per finding id to `decisions.csv` instead of one row for the group.

* `czech_language_content_mislabeled_slovak` (baseline:highdup, 495,166 docs): A subset of documents labelled slk_Latn with high pipeline confidence actually contain Czech-language text (or a Czech/Slovak code-mixed page), as shown by an independent identifier (lingua_top, somet  
  `lingua_top = 'cs' OR fasttext = 'cs'`
* `czech_documents_labeled_slovak` (baseline:random, 452,288 docs): Some documents are written in standard Czech, not Slovak, but are labeled 'slk'. These are genuine cross-lingual contamination (not just code-switching), detectable when fasttext or lingua_top indepen  
  `language = 'slk' AND (fasttext = 'cs' OR (lingua_top = 'cs' AND lingua_top_p >= 0.5))`
* `czech_text_mislabeled_slovak` (baseline:random, 449,669 docs): A minority of documents are written mostly or entirely in Czech (distinct vocabulary/grammar such as 'brambory', 'který se nachází', 'vytvořila') but are labeled as Slovak, reflecting the pipeline's d  
  `language = 'slk' AND (fasttext = 'cs' OR (lingua_top = 'cs' AND lingua_top_p > 0.5))`
* `czech_documents_mislabeled_as_slovak` (baseline:lowconf, 412,528 docs): A substantial share of documents labelled slk with low language_score are actually Czech: fasttext (and often langdetect/lingua_top) identify them as 'cs', and the visible text uses Czech grammar/voca  
  `language = 'slk' AND fasttext = 'cs'`
* `non_slovak_language_mislabeled` (baseline:random, 331,892 docs): Some documents labeled language=slk are not Slovak at all (or only marginally contain Slovak text): at least two of the three independent language identifiers (fasttext, langdetect, lingua_top) disagr  
  `language = 'slk' AND ((fasttext <> 'sk')::int + (langdetect <> 'sk')::int + (lingua_top <> 'sk')::int) >= 2`
* `czech_content_mislabeled_slovak` (baseline:lid_disagree, 114,525 docs): A recurring subset of documents is written substantially or entirely in Czech (recipes, forum posts, product boilerplate, cookie/legal notices) but is labeled slk_Latn, apparently because Czech and Sl  
  `language='slk' AND fasttext='cs' AND langdetect='cs'`
* `czech_documents_misclassified_as_slovak` (baseline:lowconf, 114,525 docs): A large share of documents are actually Czech, not Slovak, but were labelled 'slk' by the pipeline. This is evidenced by both independent language identifiers (fastText and langdetect) agreeing on 'cs  
  `language = 'slk' AND fasttext = 'cs' AND langdetect = 'cs'`
* `non_slovak_content_mislabeled_slovak_other_languages` (baseline:highdup, 102,258 docs): A small but identifiable set of documents are not Slovak at all (English, or bilingual boilerplate with Polish) yet are labelled slk_Latn, generally with a language_score noticeably below the near-1.0  
  `fasttext = langdetect AND langdetect = lingua_top AND fasttext != 'sk' AND language_score < 0.99`
* `unrelated_language_contamination` (baseline:lowconf, 63,195 docs): A substantial subset of documents are not Slavic-language text at all but English (and occasionally Polish, Russian, German, Turkish) pages — product listings, hotel booking pages, app stores, code do  
  `language = 'slk' AND fasttext = langdetect AND fasttext NOT IN ('sk','cs')`
* `english_documents_mislabeled_as_slovak` (baseline:lowconf, 51,407 docs): A recurring set of documents is written almost entirely in English (English book blurbs, product/company descriptions, academic abstracts, UI strings on .sk sites) yet carries the slk label, with fast  
  `language = 'slk' AND fasttext = 'en' AND langdetect = 'en' AND lingua_top = 'en'`
* `english_documents_labeled_slovak` (baseline:random, 51,407 docs): Some documents are actually written in English but are labeled 'slk' with a passing language_score, even though all three independent language identifiers (fasttext, langdetect, lingua) agree the lang  
  `language = 'slk' AND fasttext = 'en' AND langdetect = 'en' AND lingua_top = 'en'`
* `czech_slovak_code_switched_docs` (agent:rep2, 44,251 docs): A systematic subset of documents are Czech-language or heavily Czech/Slovak code-switched, not clean Slovak, yet are labelled language='slk' with high language_score. This mostly comes from (a) Slovak  
  `fasttext='cs' AND langdetect='cs' AND lingua_top='cs'`
* `english_dominant_travel_ecommerce_pages` (baseline:lid_disagree, 42,808 docs): Travel/booking/e-commerce aggregator pages (hotel listings, product catalog pages) are labeled Slovak with high confidence even though their substantive body content — user reviews, product/comic desc  
  `language='slk' AND fasttext='en' AND langdetect='en' AND lingua_top='en' AND domain NOT LIKE '%.firebaseapp.com' AND domain NOT LIKE '%.web.app'`
* `czech_text_mislabeled_as_slovak` (agent:rep1, 31,795 docs): A systematic slice of documents are substantially or entirely Czech-language text (product data, forum posts, cookie notices, thesis metadata, Pinterest boards) that the corpus nonetheless labels as S  
  `fasttext='cs' AND langdetect='cs' AND lingua_top='cs' AND NOT (domain LIKE '%.firebaseapp.com' OR domain LIKE '%.web.app')`

**Description.** A systematic subset of documents are Czech-language or heavily Czech/Slovak code-switched, not clean Slovak, yet are labelled language='slk' with high language_score. This mostly comes from (a) Slovak e-commerce sites that paste Czech-language product descriptions/reviews verbatim from shared CZ/SK catalogs and (b) cz.pinterest.com / forum pages whose captions and comments mix Czech and Slovak. Because Czech and Slovak are highly mutually intelligible, the pipeline's own LID and all three shipped auxiliary LIDs (fasttext, langdetect, lingua) confidently but wrongly agree that many such documents are Slovak, and even when they agree the document is Czech, the corpus still ships it labelled slk.

**Selector.** `fasttext='cs' AND langdetect='cs' AND lingua_top='cs'`

**Prevalence.** 44,251 of 26,470,482 (0.1672%), exact on the full corpus.

**Overlap with the obvious static slices.** LID-Disagree 100%, LowConf 58%, HighDup 0%

**Auditor's own precision estimate.** 0.7

**Auditor's stated likely false positives.** Genuinely Slovak documents (colloquial forum speech, short lists of proper nouns/brand names, or terse product listings) that confuse all three external language identifiers into guessing Czech even though the corpus's own slk label is correct.

**Fresh examples the auditor never saw:**

* `<urn:uuid:5f1cf043-61a9-47f0-83d4-d79e389aa406>` <https://sk.pinterest.com/danamartinkovic/>

  ```
  Nepečená torta z kondenzovaného mlieka: Včera som túto tortu pripravila kamoške na oslavu narodenín a hneď si všetci pýtali recept!
  Nepečené krémové kocky pripravené už za 15 minút! Sú naozaj vynikajúce!
  Bez cukru, bez mouky a hlavně za 10 minut připraven cheesecake s malinami | NejRecept.cz
  Vynikající koblihy (buchtičky) z trouby | NejRecept.cz
  Kočičí očka bez mouky | NejRecept.cz
  Míša řezy podle Haanky | NejRecept.cz
  Famózne pudingové kocky so šľahačkou – najlepší dezert aký ste kedy mali! | Chillin.sk
  Perníkové muffinky plnené džemom | Angie bakes
  Anise Spice Peyote Bead Pattern, Bracelet Cuff, Bookmark, Seed Beading Pattern Miyuki Delica Size 11 Beads - PDF Instant Download by SmartArtsS
  ```

* `<urn:uuid:2d6193b6-fa98-4190-858d-c08dfbea50e4>` <https://list.hw.cz/pipermail/hw-list/2006-September/283030.html>

  ```
  Ako zmotat kabel do spiraly?
  balu@home
  email@example.com
  Úterý Září 26 23:12:00 CEST 2006
  vykonovy test dopadol az prekvapujuco dobre :-)
  Tlacil som do toho ca 250W@600MHz a teplota kabla na prvych zavitoch
  bola do 45 °C. Mam aj infrafotky ale neviem ich dostat z toho zas*
  kramu... Zajtra mi s tym niekto urcite pomoze takze poslem :-)
  b.
  firstname.lastname@example.org wrote:
  > Ještě by to chtělo výkonový test - kdy to hořet začne :-). Jakou má teď ten kabel teplotu ?
  >
  > Martin.
  >
  ```

* `<urn:uuid:5fd5713e-5abf-4af8-be05-06479ed2d1cf>` <https://hurmaninvesterarpdqn.web.app/33194/4830.html>

  ```
  Prístup k e-mailovému účtu bez hesla
  19. říjen 2015 U uživatelských účtů lze i ve Windows 10 nastavit automatické (nebo zloděj) získá ihned po jeho spuštění přístup ke kompletnímu obsahu.
  Možno vás zaskočil fakt, že mail bol poslaný z vašej adresy, pretože vidíte, že v políčku odosielateľa ste vy sám. Je to ale len klam. Tiež je potrebné prístup k e-mailovému účtu cieľového alebo svojho telefónu. Cieľová osoba by pravdepodobne zistil, že som bol hacknut, ak nie okamžite potom nakoniec.
  12.02.2021
  Váš poskytovatel e-mailu vám poslal odkaz na resetování hesla. Zapomněli Po dokončení přidání účtu Gmail můžete přidat další e-mailový účet nebo vybrat abyste ověřili, že jste osoba, která se pokouš
  ```

## G03: loan_gambling_seo_spam

**Members (1).** A large group can mix related but distinct claims; if so, add a row per finding id to `decisions.csv` instead of one row for the group.

* `loan_gambling_seo_spam` (baseline:random, 226,542 docs): A set of documents built around 'quick loan' (pôžička) and gambling/casino (kasino, automaty, poker) keywords contain incoherent, topic-jumping text that reads as machine-stitched or spun content opti  
  `url ILIKE '%pozick%' OR url ILIKE '%kasino%' OR url ILIKE '%casino%' OR domain LIKE '%.xyz'`

**Description.** A set of documents built around 'quick loan' (pôžička) and gambling/casino (kasino, automaty, poker) keywords contain incoherent, topic-jumping text that reads as machine-stitched or spun content optimized for search ranking rather than genuine articles — a single document abruptly mixes betting-bonus copy with unrelated facts (train schedules, football trivia, travel descriptions, tourist landmarks).

**Selector.** `url ILIKE '%pozick%' OR url ILIKE '%kasino%' OR url ILIKE '%casino%' OR domain LIKE '%.xyz'`

**Prevalence.** 226,542 of 26,470,482 (0.8558%), exact on the full corpus.

**Overlap with the obvious static slices.** LID-Disagree 3%, LowConf 0%, HighDup 0%

**Auditor's own precision estimate.** 0.6

**Auditor's stated likely false positives.** The keyword-based selector will also catch genuine finance/travel articles that legitimately discuss loans or a casino as a place name, and any .xyz-domain site that is not actually spam; the url/domain heuristic is a proxy for a topical-incoherence judgment that SQL alone cannot verify.

**Fresh examples the auditor never saw:**

* `<urn:uuid:3351c5b5-644f-499b-b79e-c595650b32f0>` <https://www.self-x.sk/pozicky-cez-telefon-ihned-piestany>

  ```
  SMS pôžičky v súčasnosti nahradili rýchle pôžičky cez internet.
  Spoznajte s nami rozmanitosť gastronómie, ktorá podčiarkuje fakt, že sa historicky jednalo o križovatku kultúr a rôznych národností.
  Bankové i nebankové spoločnosti vám ponúkajú rýchle pôžičky bez dokladovania príjmu, všetko prebehne rýchlo a jednoducho, už aj cez telefón.
  Vo filme Hviezdne vojny: Impérium vracia úder majú povstalci svoje vesmírne lode ukryté v podzemnej…
  Washington (Washington D.C.), získalo meno podľa Georga Washingtona, prvého prezidenta Spojených štátov, ktorý sa preslávil aj ako vojnový vodca americkej revolúcie.
  Pri tipovaní je dôležité sledovať, kde sa konkrétny zápas uskutoční, pretože veľa tímov bude hr
  ```

* `<urn:uuid:319d3e57-a1e3-488d-bf07-5d89562642e9>` <https://www.vratenie-dane.sk/rychla-pozicka-cez-telefon-bardejov>

  ```
  Mnoho z týchto prírodných úkazov nie je voľne prístupných verejnosti, ale stále je tu dostatok jaskýň, ktoré môžeme navštíviť.
  Chceli by ste prostredníctvom týchto hier osláviť medzinárodný deň psov? Zaujímalo by vás, kde si tieto hry môžete zahrať? Nájdete ich v casíne 7Signs.
  Projekt Oktagon Underground pokračoval už svojím piatym turnajom a v ňom sme mohli vidieť finálové zápasy českých pyramíd, ale aj atraktívne superfighty.
  Nie každý deň je nedeľa, a to platí aj v hre.
  Existuje niekoľko typov pôžičiek – rýchla online pôžička, pôžička bez registra, rýchle pôžičky do výplaty, rýchle pôžičky do 350€, pôžičky pre nezamestnaných, pôžička pre mladých, úver na auto či na svadbu a mnoho iných.
  ```

* `<urn:uuid:07adf615-148c-41b8-a380-5c23cd88e6e5>` <https://www.qq365.xyz/automaty-jackpot-cele-filmy>

  ```
  - złożysz promocyjny wniosek o rachunek umożliwiający regularne oszczędzanie Moje cele,
  Filmy, hry či softvér - za to všetko viete zaplatiť Paysafecard.
  Díky stránkám, jako jsou Automaty zdarma, jste mohli začít hrát na výherních automatech doma nebo ve vaší kanceláři, a to kdykoli.
  Los Colchoneros sú na čele La Ligy s trojbodovým náskokom (a zápasom k dobru) pred Realom Madrid.
  Opäť je tu nová vlna zábavy a možností na to vyhrať parádny jackpot. Kasíno je od utorka bohatšie o štyri hry, s ktorými prežijete neopakovateľné dobrodružstvo.
  Ak to umožňujú podmienky bonusu, tak áno. Niektoré bonusy sú, dokonca, exaktne použiteľné na hracie automaty od tohto obľúbeného výrobcu. Týka sa to, napríkl
  ```

## G04: adult_spam_farm_wordsalad

**Members (4).** A large group can mix related but distinct claims; if so, add a row per finding id to `decisions.csv` instead of one row for the group.

* `adult_spam_farm_wordsalad` (agent:rep2, 102,474 docs): A cluster of throwaway-domain adult/porn spam sites contribute documents that are not coherent Slovak prose but auto-generated word-salad: SEO tag lists, stitched keyword fragments, and repeated boile  
  `n_bad_words >= 3`
* `porn_spam_keyword_farm` (agent:main, 94,946 docs): A second, separate spam network of thousands of randomly-named domains (English dictionary-word-like names + generic gTLDs/ccTLDs such as .com/.me/.fr/.bike/.online/.info/.nl/.it/.us/.br) hosts keywor  
  `n_bad_words >= 3 AND domain NOT LIKE '%.sk' AND domain NOT LIKE '%.cz'`
* `unfiltered_adult_content` (baseline:lid_disagree, 79,248 docs): Explicit pornographic content is present in the Slovak slice despite the pipeline recording a profanity-match signal (n_bad_words) that could have been used to filter it; documents with several profan  
  `language='slk' AND n_bad_words >= 4`
* `porn_doorway_spam_network` (agent:rep1, 52,354 docs): A second, distinct content-farm/doorway-page spam network -- unrelated to the firebaseapp/web.app finance farm -- serves auto-generated pornography aggregator pages under ~60+ unrelated-looking domain  
  `n_bad_words > 5`

**Description.** A cluster of throwaway-domain adult/porn spam sites contribute documents that are not coherent Slovak prose but auto-generated word-salad: SEO tag lists, stitched keyword fragments, and repeated boilerplate phrases (e.g. "zadarmo čierne Lesbičky Sex Movies" injected dozens of times) built by a domain-spinning template. The corpus's own language_score is near-perfect (often >0.99) and all three shipped LID tools agree on 'sk', yet the "documents" are not naturally authored Slovak text and provide no usable linguistic signal.

**Selector.** `n_bad_words >= 3`

**Prevalence.** 102,474 of 26,470,482 (0.3871%), exact on the full corpus.

**Overlap with the obvious static slices.** LID-Disagree 11%, LowConf 2%, HighDup 0%

**Auditor's own precision estimate.** 0.9

**Auditor's stated likely false positives.** Long, legitimate documents that legitimately discuss sex education, health, or relationships in depth and happen to accumulate 3+ profanity-list hits (e.g. a sex-therapy forum thread) rather than being spam-farm content; these appear to be a small minority based on the two 25-document samples, but were not separately quantified.

**Fresh examples the auditor never saw:**

* `<urn:uuid:a116928f-6d21-454b-85c1-18651b236295>` <https://agari.us/chlpat-vagny-ierne-dievat.html>

  ```
  Od najdlhšieho. Naolejovaná čierna divoška to poriadne roztočí. Jožko sa pýta otca: Ocko ako vyzerá vagína pred súložou?
  Najnovšie videá zadarmo - Chlpaté vagíny.
  Pinky XXX orgie
  Pred 3 rokmi. 01:09. Čierne Vaginy, Sexi Chlpate Vaginy, Bábika, Čierna A Ebony. Tvoje pohlavné chlpatý a tmavší ako zvyšok. Dievčatá to majú radi do zadočku 12:26. Vaginy, Sexi Chlpate Vaginy, Jazyk, Špinavé, Čierne Videos, Učiteľ. Naposledy Pridané Chlpaté Kundy Japanese partners want to spice up sexual life and guy fucks chicks vagina on the beach. Pozrite si Najnovšie porno videá v porno kategórií Veľké prsia. Skinny lezzies jesť chlpaté vagíny 05:34 · chudá, chlpatý. Naše modelky sú hrdé ukázať ich neoholené dá
  ```

* `<urn:uuid:427d8117-8205-4480-a426-bd771c0f9376>` <https://accesslocator.net/s-strieka-orgazmy-relne.html>

  ```
  A ano zena pri orgazme strieka 8-))To je pecka orgazmus,ale ma to aj. Latina strieka šťavičku 25:11. Mladá teenka predvádza striekanie 24:53 Squirting je mokrý ženský orgazmus, ktorý majú ženy pri orgazme. Toto video bolo pridané na amatérske hot sú striekať orgazmy reálne análny kategórie, viac podobných videí šialený amatérske orgazmy na amatérske, hot, girl, hardcore, kompilácie. Pozri si Najpozeranejšie porno videá v porno kategórií Striekanie dovnútra, vyber si z 861 najlepších porno videí na sledovanie zdarma, usporiadaj si ich podľa.
  Mokré piči zblízka masturbácia reálne pulzujúce orgazmy. Zuzana: "Môjmu partnerovi robí maximálne dobre, keď ma vidí striekať.
  Ide o reálnu medicínsku di
  ```

* `<urn:uuid:4a15db37-b865-4602-8b37-42bac0301d84>` <https://bananapepper.fr/tesn-dieva-maika.html>

  ```
  Vieš čo to je. Milujem spôsob akým cítiš, dievča. Ivan Bednárik si posvietil na párty oblečenie známych tvárí. Najnovšie na Markíze. Láska im dopriala: Toto sú nové fotky čiernych Babes slovenského šoubiznisu · Speváčka tesne pred pôrodom: Tesné dievča mačička fotka hore mačočka.
  Jedno je čisto biele (chlapec) a druhé čierne(dievča) so šedými pásikmi. Duel sa uskutoční tesné dievča mačička newyorskej Madison Square Garden, ktorá je považovaná za "Mekku boxu".
  Dievčatá budú k odberu o tri týždne, teda v druhej polovici júla.
  Otec je čistokrvný biely Maine Coon a matka štandartná čierna mačka. Bolo to vidieť na tom chvostíku, ktorý malo mačiatko stiahnuté a už ku koncu videa sa ani nebránila t
  ```

## G05: slo_prefix_machine_translated_farm

**Members (1).** A large group can mix related but distinct claims; if so, add a row per finding id to `decisions.csv` instead of one row for the group.

* `slo_prefix_machine_translated_farm` (agent:rep1, 73,835 docs): A third distinct content-farm network: hundreds of unrelated-looking, seemingly hijacked/repurposed domains (e.g. slo.andhramedicalcollegevizag.com, slo.istanbulmedicine.com, slo.kelinvestgroup.com, s  
  `domain LIKE 'slo.%'`

**Description.** A third distinct content-farm network: hundreds of unrelated-looking, seemingly hijacked/repurposed domains (e.g. slo.andhramedicalcollegevizag.com, slo.istanbulmedicine.com, slo.kelinvestgroup.com, slo.orsitaning.ru) all serve the same machine-translated content mirror under a 'slo.' (Slovak) subdomain. Content is overwhelmingly pseudo-medical/health/lifestyle articles whose URL slugs are transliterated Russian (e.g. 'diagnostika-raka-jaichek-u-muzhchin', 'kod-po-mkb-mehanicheskaja-zheltuha'), indicating the same Russian-origin article set has been bulk machine-translated into Slovak (and presumably many other languages via sibling subdomain prefixes) and republished across this domain farm. Unlike the firebaseapp.com spam, the translated text is fluent and grammatically coherent single-topic prose, so it reads as legitimate native Slovak and would not be caught by quality heuristics, but it is not organically authored Slovak content and the same articles are repeated near-verbatim across dozens of domains.

**Selector.** `domain LIKE 'slo.%'`

**Prevalence.** 73,835 of 26,470,482 (0.2789%), exact on the full corpus.

**Overlap with the obvious static slices.** LID-Disagree 0%, LowConf 0%, HighDup 0%

**Auditor's own precision estimate.** 0.9

**Auditor's stated likely false positives.** A small number of domains under this prefix could coincidentally be legitimate Slovak-prefixed sites unrelated to the farm; none were observed in the 12-document sample, but the prefix match alone is a heuristic, not a certified membership test.

**Fresh examples the auditor never saw:**

* `<urn:uuid:ef25b822-458a-4b25-bfc9-ec5be6edf652>` <https://slo.healthycatchups.com/produkty-pitanija-kategorii.html>

  ```
  Užitočná a pohodlná klasifikácia potravinárskych výrobkov do skupín od odborníkov WHO rozdeľuje produkty do 5 hlavných skupín. Pomáha ľahko a správne budovať svoju stravu bez toho, aby ste sa príliš starali o rôzne výpočty.
  Klasifikácia potravinárskych výrobkov skupinami odborníkov WHO nám pomáha rýchlo a jednoducho rozhodnúť nielen o tom, čo jesť, ale aj o množstve potravín, ktoré potrebujeme jesť počas dňa. Nasledujúce infografiky ukazujú 5 hlavných skupín potravín, ako aj počet porcií, ktoré odborníci odporúčajú na uspokojenie našich potrieb.
  5 skupín potravín pre zdravú výživu
  Distribúcia potravín podľa skupín je založená na ich podobnom vplyve na naše telo vďaka jeho nutričným vlastnost
  ```

* `<urn:uuid:a081900e-1d34-4dc6-bd62-9873eab28a29>` <https://slo.eastdevonbusinessclub.com/biznes-molodost-dostavka-edy.php>

  ```
  Dnes nie je potrebné nakupovať v obchodoch, pretože všetko, čo potrebujete, si môžete objednať cez internet. Okrem toho nie je potrebné ani tráviť čas na varenie, kde je lepšie objednať jedlo dodané do vášho domova.
  Podnik vytvorený v tomto odvetví služieb môže byť veľmi ziskový a okrem toho má mnoho vyhliadok. Nepochybne je pre neho ešte väčšia konkurencia, ale s túžbou a tvrdo pracovať, zistíte, že vaša nika, ktorá vás urobí úspešnou.
  Dôležité rady pre podnikateľov: nestrácajte čas ani na jednoduché rutinné úlohy, ktoré môžu byť delegované. Premeňte ich na voľnej nohy "Vykonávanie". Garantovaná kvalitná práca včas alebo vrátenie peňazí. Ceny dokonca aj pre rozvoj miest začínajú od 500 rubľ
  ```

* `<urn:uuid:853b86a8-974d-4304-9627-08ce118265b7>` <https://slo.ktopclinic.com/pochemu-u-zhenshhin-byvajut-prilivy>

  ```
  Návaly horúčavy s menopauzou: čo to je, príznaky
  Vážení odberatelia, dobré popoludnie! Dnes budeme diskutovať o príčinách návaly horúčavy u žien. Zvážime, o čo ide a prečo k nim dôjde..
  V jednom zo starých predrevolučných novín sa uvádza, že prílivy a odlivy postihujú hlavne ženy, ktorých telo nemá draslík. Tieto údaje potvrdzujú aj štúdie moderných vedcov..
  Podľa nich, aby žena necítila príliv, musí jesť hrozienka, sušené marhule, pohánky, vlašské orechy, med a citróny. Tieto potraviny obsahujú veľa draslíka. Draslík sa tiež vyskytuje vo veľkých množstvách v banánoch..
  Tides - prvý posol menopauzy
  Podľa väčšiny lekárov sú návaly horúčavy prejavom menopauzálneho syndrómu, ktorého charakteris
  ```

## G06: spun_macaronic_template_text

**Members (1).** A large group can mix related but distinct claims; if so, add a row per finding id to `decisions.csv` instead of one row for the group.

* `spun_macaronic_template_text` (baseline:lid_disagree, 18,708 docs): A set of location/accommodation listing pages (observed systematically on domain kamsi.sk) use algorithmically spun text that ungrammatically mixes Slovak and Czech words and synonyms (e.g. 'a lebo',   
  `language='slk' AND domain='kamsi.sk'`

**Description.** A set of location/accommodation listing pages (observed systematically on domain kamsi.sk) use algorithmically spun text that ungrammatically mixes Slovak and Czech words and synonyms (e.g. 'a lebo', 'prípadne', 'treba') to generate ostensibly unique per-town pages. This is not natural language in either Slovak or Czech, and is templated near-duplicate filler rather than genuine linguistic content.

**Selector.** `language='slk' AND domain='kamsi.sk'`

**Prevalence.** 18,708 of 26,470,482 (0.0707%), exact on the full corpus.

**Overlap with the obvious static slices.** LID-Disagree 69%, LowConf 1%, HighDup 0%

**Auditor's own precision estimate.** 0.8

**Auditor's stated likely false positives.** Any kamsi.sk pages that use normal, grammatical Slovak listing text rather than the synonym-spun template (not observed in this sample but plausible for other sections of the site).

**Fresh examples the auditor never saw:**

* `<urn:uuid:d4319dc7-7a06-4387-a18a-015228ce6a98>` <https://kamsi.sk/velky-krtis/apartmany/>

  ```
  Štylové či prípadne vybrané apartmány v Veľkom Krtíši na zaujímavých miestach a s roznými službami;) Naplánujte výlet s priateli do Veľkého Krtíša a spojte to s zážitky lebo treba výletmi či zámky;) Nalézáte sa u nás na webe s možnosťou ubytovania v kategórii určené pro apartmány Veľký Krtíš. Odporúčajeme využit všechny naše možnosti vyhľadávánia apartmánů na základě počtu osob či pokojov, kvality, ceny, služieb pro ještě špecifické vyhľadávánie apartmánů v Veľkom Krtíši či treba možná toho čo by vás mohlo zaujmout!
  Až buďeťe v Veľkom Krtíši běžte si stráviť s dětmi jasně lacnější ubytovanie ( apartmány ) v následující obci za neuveritelných podmienek .
  Vyberte si z komplexné ponuky ubytovan
  ```

* `<urn:uuid:5d2b17ba-0743-4f26-be9b-445b57cf03df>` <https://kamsi.sk/znojmo/obec-dyjakovice/>

  ```
  Vkusné lebo trebárs kvalitné ubytovanie v Dyjákovice s vysokým štandardem ubytovania. Práve ste na našich stránkách s ponukou ubytovania v části určené pro oblasť Dyjákovice;) Odporúčame použít všechny naše volby filtrácie ubytovanie na základě uvedenia regionu - Dyjákovice - či treba ceny, služieb, počtu pokojov či osob, kvality pro ještě konkrétnějšie zohnánie ponuky pobytov naprieklad na služobnú cestu a dokonce toho ubytovanie v Dyjákovice co by se vám mohlo páčiť!
  Pokud nekdy buďeťe v mestě Dyjákovice jeďte si dopriať s dětmi sakra lacné ubytovanie v následující obci za pár eur ;)
  Vyberte si z nepreberné ponuky pobytov v oblasti Dyjákovice proslulou jedlom a pitím , kľudom prípadne muze
  ```

* `<urn:uuid:301ab60a-70a8-4034-a194-5633e05b663c>` <https://kamsi.sk/zarnovica/bazen-aquapark/>

  ```
  Skombinujte aquapark a príjemné ubytovanie v Žarnovicích v kľudných lokalitách a možnosťou relaxácie:) Vyjeďte s partou a skombinujte aquapark s zážitky či prípadne pohodou či pamiatkami v lokalite Žarnovica! Zkúste všechny naše ponuky filtrovania druhov ubytovanie v Žarnovicích na základě vopsánia lokality prípadne kvality, služieb, počtu osob či pokojov, ceny pro ještě presňajší objavenie ubytovanie či také toho čo práve hľadáte a naviac možete zkombinovať vše s Vaší láskou, ktorým aquapark určito je! Ocitli jste sa u nás na kamsi.sk s ponukou ubytovania v kategórii zasvecené pro gurmány aquaparku;)
  Pokud nekdy buďeťe v Žarnovicích zkúste si vychutnať s rodinou lacné ubytovanie ( aquaparky
  ```

## G07: cookie_consent_boilerplate_dominant

**Members (1).** A large group can mix related but distinct claims; if so, add a row per finding id to `decisions.csv` instead of one row for the group.

* `cookie_consent_boilerplate_dominant` (baseline:highdup, 11,676 docs): A very large share of documents open with (and are sometimes almost entirely composed of) generic cookie-consent / GDPR notices rather than substantive page content. Because the crawler/extractor capt  
  `LOWER(SUBSTR(text,1,250)) LIKE '%cookie%' OR LOWER(SUBSTR(text,1,250)) LIKE '%súbory cookie%'`

**Description.** A very large share of documents open with (and are sometimes almost entirely composed of) generic cookie-consent / GDPR notices rather than substantive page content. Because the crawler/extractor captured this legal boilerplate as the primary text, many 'unique' post-dedup documents contribute little genuine linguistic content and are highly repetitive in structure/vocabulary across completely unrelated sites.

**Selector.** `LOWER(SUBSTR(text,1,250)) LIKE '%cookie%' OR LOWER(SUBSTR(text,1,250)) LIKE '%súbory cookie%'`

**Prevalence.** 11,676 of 2,034,896 (0.5738%), measured on the 1-in-13 text sample.

**Overlap with the obvious static slices.** LID-Disagree 6%, LowConf 1%, HighDup 2%

**Auditor's own precision estimate.** 0.65

**Auditor's stated likely false positives.** Pages that mention 'cookie' briefly in the first 250 characters but then continue with substantial unique content afterward (e.g. a product page whose consent banner is short and followed by rich description); also legitimate standalone cookie-policy documents, which are 'about' cookies rather than contaminated by them.

**Fresh examples the auditor never saw:**

* `<urn:uuid:2939ec96-2f5d-463f-bb5b-1837f752f179>` <https://www.egalanteria.sk/www-egalanteria-sk/eshop/17-1-priadze-JAR-LETO/0/5/4536-3-nitka-Cherubinka-Silk-2000-m/description>

  ```
  S cieľom uľahčiť užívateľom používať naše webové stránky využívame cookies. Používaním našich stránok súhlasíte s ukladaním súborov cookie na vašom počítači / zariadení. Nastavenia cookies môžete zmeniť v nastavení vášho prehliadača.
  Cherubínky sú unikátne ručne navíjané vrstvené tenké priadze s dlhými farebnými prechodmi.2000 metrové klbko odporúčame použiť pre topy a svetríky veľkostí XXL a väčšie ak sa chystáte použiť tuhší vzor, alebo letné šaty veľkostí XL-XXL.Dajú sa pliesť alebo háčkovať a vďaka plynulým farebným prechodom z nich vyrobíte naozaj unikátne kúsky.
  ```

* `<urn:uuid:1dc1ffe6-a4b9-49ef-a47d-14e69b1d2eba>` <https://www.erko-nabytok.sk/Sedacia-suprava-v-tvare-U-ekokoza-cierna-latka-cierny-melir-prava-ALMA-d3954.htm>

  ```
  S cieľom uľahčiť užívateľom používať naše webové stránky využívame cookies. Používaním našich stránok súhlasíte s ukladaním súborov cookie na vašom počítači / zariadení. Nastavenia cookies môžete zmeniť v nastavení vášho prehliadača.
  Sedacia súprava v tvare U, ekokoža čierna/látka čierny melír, pravá, ALMA
  doprava zdarma
  Vaše hodnotenie:
  Ďakujeme za Vaše hodnotenie
  0x
  skladom
  Kompletné špecifikácie
  Elegantná rohová celočalúnená sedacia súprava v tvare U ALMA
  pravé prevedenie,
  materiál: ekokoža čierna/látka šenil Berlín 02 čierný melír,
  rozmery (ŠxHxV): 342x202/160x63 cm, výška a hĺbka sedu: 39x63 cm.
  ```

* `<urn:uuid:1485db3e-1fd3-463c-9d7c-54d87aa2761f>` <https://www.autovip.sk/autoziarovky-h9/>

  ```
  Autožiarovky (H9)
  Akcia
  Kód: 64213
  Žiarovky rady OSRAM sú vysoko spolahlivé a ponúkajú vynikajúci pomer cena/výkon. Žiarovky OSRAM sú dobrou voľbou pre zákazníkov ocenujúcich dobrú kvalitu.
  Používáme cookies, aby sme Vám umožnili pohodlné prehliadanie webu a vďaka analýze prevádzky webu zlepšujeme jeho funkcie, výkon a použiteľnosť. Viac informácií.
  Nastavenie
  Prihláste sa prosím znovu
  Ospravedlňujeme sa, ale Váš CSRF token pravdepodobne vypršal. Aby sme mohli Vašu bezpečnosť udržať na čo najvyššej úrovni, potrebujeme, aby ste sa znovu prihlásili.
  Ďakujeme za pochopenie.
  ```

## G08: incoherent_spun_affiliate_content

**Members (1).** A large group can mix related but distinct claims; if so, add a row per finding id to `decisions.csv` instead of one row for the group.

* `incoherent_spun_affiliate_content` (baseline:random, 9,096 docs): A set of documents on loan/casino/betting affiliate sites contain fluent-at-the-sentence-level Slovak that is nevertheless topically incoherent across the document — unrelated sentences (tourism facts  
  `domain IN ('terrapermonia.sk','blueplast.sk','prachova.sk','ufophoenix.xyz','dailyufosightings.xyz','lubicon.cz','obecweb.sk')`

**Description.** A set of documents on loan/casino/betting affiliate sites contain fluent-at-the-sentence-level Slovak that is nevertheless topically incoherent across the document — unrelated sentences (tourism facts, sports trivia, legal notices) are stitched next to gambling/loan promotional copy with no topical continuity, indicating spun or automatically assembled SEO content rather than genuine authored text. Unlike the doorway-domain cluster, these pass language identification cleanly because each sentence is well-formed Slovak.

**Selector.** `domain IN ('terrapermonia.sk','blueplast.sk','prachova.sk','ufophoenix.xyz','dailyufosightings.xyz','lubicon.cz','obecweb.sk')`

**Prevalence.** 9,096 of 26,470,482 (0.0344%), exact on the full corpus.

**Overlap with the obvious static slices.** LID-Disagree 2%, LowConf 0%, HighDup 0%

**Auditor's own precision estimate.** 0.6

**Auditor's stated likely false positives.** This selector is a closed list drawn only from the sample and will not generalize to the full corpus; a broader keyword-based heuristic (url containing 'pozicka'/'kasino'/'poker') would also catch coherent, legitimate loan-comparison or casino-review articles such as trhoviskopoziciek.sk, which is fluent and topically consistent despite the same keywords.

**Fresh examples the auditor never saw:**

* `<urn:uuid:b8d47cf2-05da-4473-90f9-a0c085650bac>` <https://www.ufophoenix.xyz/hrajte-automaty-pronajmu-ostrava>

  ```
  Hrajte automat 2 Gods: Zeus vs Thor Dualspin online zadarmo v demo režime bez nutnosti stiahnuť si tento výherný automat ako aj bez registrácie
  HRAJTE KAJOT AUTOMATY S 75 FREE SPINS ZDARMA Hrajte sa, ale s rozumom
  Softvér: SYNOT Games | Počet valcov: 5 | Žáner: Ovocné automaty | Počet výherných línii: 10
  automaty delíme podľa princípov ich fungovania, na mechanické, elektronické a digitálne.Prostredníctvom nich môžu získať voľné točenia na automaty, skutočné peniaze alebo Benefit body.
  Sú to automaty ako napríklad Joker Strong, Firebird Double 27, Armed'n'Wild, Reel Sheriff a ďalšie.
  automaty volné tocenia za registraciusynot automaty zdarma 2022
  Raz sa zrodila remíza a raz vyhrala Ostrava v
  ```

* `<urn:uuid:d46ee59e-0cfb-4fad-8ca2-8c09e4d5663d>` <https://www.dailyufosightings.xyz/android-poker-game-of-changing>

  ```
  Zahrajte si herný automat Game of Thrones v niektorom z našich odporúčaných online kasín.
  Poker sa hrá s balíčkom francúzskych kariet (52) (v niektorých verziách pokru sa používajú aj žolíky).Návod jak používat pokerový software Poker Tracker 3:
  Spoločnosť Relax Gaming v súčasnosti dodáva spoločnosti Kindred exkluzívny poker a bingo obsah spolu s vysoko kvalitným obsahom v kasínach.
  Hoci video poker nepatrí medzi hry, ktoré by ponúkalo každé jedno slovenské online kasíno (a to platí pre celý svet), je to hra, ktorú by ste nemali len tak odsudzovať.Jednoducho kliknete na stránku online kasína a bez toho, aby ste sa registrovali či uviedli akékoľvek údaje, si môžete vychutnať niektorú z vašich
  ```

* `<urn:uuid:5c48885d-5104-4388-a1f0-90ddf1c1e64d>` <https://www.obecweb.sk/osemfinale-6-12-portugalsko-vz-brazilie-fortuna-kurzy>

  ```
  Až v osemfinále ho zastavil Rafael Nadal, ktorému dokonca Američan uchmatol jeden set.
  Prvé kolo play-off, v tomto prípade osemfinále, sa hrá na 10 víťazných legov.A to ešte duel so Gillesom Müllerom v osemfinále turnaja v Sydney musel Thiem pre zranenie za stavu 6:7 a 2:2 skrečovať.
  Triple point – Venezuely, Brazílie a Guayany.
  Nakonec se stěhoval zpět do Brazílie, přesněji do SC Corinthains. Ale ani zde se nechytil a tak putoval na hostování do Sao Paula.08.Feb 2020 | 14:30 Autor: Dušan Kategória: Lacné letenky Značky: brazília rio de janeiro Južná Amerika letisko praha letenky do brazílie klm letenky do rio de janeiro
  Madeira, ktorá patrí pod Portugalsko, sa môže popýšiť čiernymi plážami,
  ```

## G09: adult_tagfarm_content_mislabeled

**Members (1).** A large group can mix related but distinct claims; if so, add a row per finding id to `decisions.csv` instead of one row for the group.

* `adult_tagfarm_content_mislabeled` (baseline:lowconf, 1,717 docs): A small but recurring set of documents are pornographic tag-aggregator pages (lists of explicit search terms/tags with minimal connecting prose) that are mostly English or template text, not genuine S  
  `n_bad_words >= 3 AND langdetect != 'sk'`

**Description.** A small but recurring set of documents are pornographic tag-aggregator pages (lists of explicit search terms/tags with minimal connecting prose) that are mostly English or template text, not genuine Slovak writing, yet are labelled 'slk'. They are identifiable by an elevated profanity/bad-word count combined with a language identifier disagreement.

**Selector.** `n_bad_words >= 3 AND langdetect != 'sk'`

**Prevalence.** 1,717 of 26,470,482 (0.0065%), exact on the full corpus.

**Overlap with the obvious static slices.** LID-Disagree 100%, LowConf 44%, HighDup 0%

**Auditor's own precision estimate.** 0.5

**Auditor's stated likely false positives.** Because only 3 of 300 sampled documents match this narrow condition, the estimate is based on a very small sample; ordinary Slovak news/forum content discussing crime or health topics with a handful of profanity-list hits (not adult-tag pages) would also match n_bad_words>=3 and dilute precision at corpus scale.

**Fresh examples the auditor never saw:**

* `<urn:uuid:0c5dac23-5acb-4960-9b51-3b34825f0096>` <https://baazzaa.com/yuong-maika-pics.html>

  ```
  Posted by Admin | in January 1, 2020 |
  Teen Mačička veľký horúce sexy Masturbácia Sólo. March 2019 | Krásna žena Yuog Watch the Best lesbian, teen, bdsm, gay. Sieť kohút sania Teen mačička prstoklad Fajčenie. Mom Loves Young Yuong mačička pics hardcore doggystyle čierne ženy sať mačička threesomes lingerie. Lesbičky Teen teenpussy nahá mačička dievča na girl porn. Mačička Porno videá | Porn Video TOP. Tehotná Masturbácia Tehotná Mačička sex mačiička Yuong mačička pics krásny.
  Prezrite si nástenku "Mačičky" používateľa Diana Bežovská na Pintereste. Mature Lady Fucks Young Cock At A Spa Report 12:00.
  Zrelé veľké čierne somáre
  Prezrite si nástenku "Cute Mačičky" používateľa Teen porno Cumshots 
  ```

* `<urn:uuid:f53ca551-294d-44e3-8927-d24b7009a943>` <https://ballyclarebid.co.uk/cum-na-jazyk-pics.html>

  ```
  Tramp knows how to cum a lot. Aroused bender. Xxxkaitrena kaf, booble com the adult search engine?
  dávať muža orálny sex
  Explosive revealing. Ramrod sucking pics free xxx video. Tasty pornstar receives her cum-hole nailed. I love cum on feet only Disclaimer. The whole time and Brown -Mocha Menage - Pop On The backdoor 08:00. Novice in natures garb pic · Hottest bedroom scenery 05:09. Miss Aysha licks buxom grannys hirsute cum-hole and eats her arse porn hd xxx 05:40 OmaHoteL awesome pics Collection Compilation hdxxx 08:07. Best Live Streaming Mistress Porn Online - 100% Free! Chatroulette: Cum na jazyku - Direct dans 03:15.
  gay orgie porno trubice
  Porn Disco @morganmcmichael @CCBCResortHotel
  ```

* `<urn:uuid:29c75daa-0afa-4368-8669-d5f674354996>` <https://cyfar.online/amuture-vide/>

  ```
  Amateur Hour play sweet, gritty guitar-pop that is exuberant and weathered, like if Keith Richards were a televangelist. Pozrite si najnovie amuture vide vide od pouvatea Chesterfield Amateur Boxing Club. Pi sa mi to. AASC is swimming at Cabarita pool in 2018-19 each Saturday from 7.
  xxx video sexye
  The IAC - British Int. Amateur Film & Video Competition IAC - Britsk medzin. Pozrite si fotky a vide na Instagrame zaznamenan na mieste Amateur Store. Pozrite si fotky a vide na Instagrame zaznamenan na mieste Hard Knocks Amateur Boxing Club. Redakn vide Vae vide Oficilne vide In moto vide Najnovie Pridaj videoNajnovie vide: od autora Amateur. Dunston Teams amateur boxing club, Gateshead. Muswell
  ```

## G10: cross_domain_loan_ad_widget_contamination

**Members (1).** A large group can mix related but distinct claims; if so, add a row per finding id to `decisions.csv` instead of one row for the group.

* `cross_domain_loan_ad_widget_contamination` (baseline:highdup, 264 docs): A large number of documents, regardless of the host site's actual topic (theater galleries, veterinary equipment, cooking forums, sports clubs, music sites, equestrian festivals), contain a near-verba  
  `text LIKE '%Naposledy pôžičku vyskúšali%' OR text LIKE '%Vyplňte nezáväznú žiadosť%' OR text LIKE '%Hana, Břeclav%' OR text LIKE '%Posledn% žiadatelia`

**Description.** A large number of documents, regardless of the host site's actual topic (theater galleries, veterinary equipment, cooking forums, sports clubs, music sites, equestrian festivals), contain a near-verbatim templated 'pôžička' (online loan) advertisement widget, including fabricated customer testimonials with the same names (e.g. 'Hana, Břeclav'). This is third-party ad/widget boilerplate that has nothing to do with the page's subject matter and is duplicated wholesale across dozens of unrelated domains, surviving deduplication because it is embedded within otherwise-unique page shells.

**Selector.** `text LIKE '%Naposledy pôžičku vyskúšali%' OR text LIKE '%Vyplňte nezáväznú žiadosť%' OR text LIKE '%Hana, Břeclav%' OR text LIKE '%Posledn% žiadatelia%'`

**Prevalence.** 264 of 2,034,896 (0.0130%), measured on the 1-in-13 text sample.

**Overlap with the obvious static slices.** LID-Disagree 2%, LowConf 0%, HighDup 4%

**Auditor's own precision estimate.** 0.9

**Auditor's stated likely false positives.** Documents from actual loan/finance-comparison businesses where this text is the site's genuine (if still templated/thin) content rather than injected off-topic ad contamination.

**Fresh examples the auditor never saw:**

* `<urn:uuid:351fa8a8-cbdd-4e88-abc8-2c9970fac9fa>` <https://www.piperi.sk/najvyhodnejsi-spotrebny-uver-2018-zilina>

  ```
  Ak máte záujem o stavebný úver, úroková sadzba sa pohybuje vo výške od 1,49 % do 1,89 %, v závislosti od ďalších pripoistení, ako je životné poistenie a poistenie bývania.
  Limski kanál leží približne 6 km severne od mesta Rovinj.
  V rámci kvalifikácie o postup na MS 2018 sa v domácom prostredí rýchlo dostalo do vedenia, ale svoj náskok neudržalo.
  - Promenády sú pokryté stĺporadím vo tvare stromov, zvlnené tvary pripomínajú potoky lávy.
  - Všeobecne: Úver Úver je flexibilnejšia forma financovania, ktorá vám umožňuje kedykoľvek získať prístup k množstvu požičaných peňazí.
  - Jako vždy Thajsko nezklamalo , super ubytování , jídlo , masáže , koupání a prima lidi - úžasnej konec 2017 a začátek roku 
  ```

* `<urn:uuid:1b84f256-2c74-4cf5-a28b-87a21e5b5726>` <https://hurmaninvesterarxwok.web.app/49906/57738.html>

  ```
  " Dobrý den. ako mám cez internet banking previesť eura do čiech na osobný účet v českých korunách " Iveta Kadlečíková 08.12.2017 - 12:28
  Máme 9,4 eura na hodinu, Německo 31,4 eura na hodinu. Tento rozdíl nás skutečně dráždí," pokračuje Středula, podle kterého se současná diskuse měla točit okolo životní úrovně v Česku, a ne okolo data vstupu do eurozóny. Přechod na jednotnou měnu si vynutí rozsáhlé přepočty peněžních částek z českých korun na eura a naopak. Pro tyto účely evropská legislativa stanoví závazná pravidla pro použití přepočítacího koeficientu a pro zaokrouhlování přepočtených částek. Rolí státu bude dbát na striktní dodržování těchto pravidel. Faktická rezignace na jakoukoli fis
  ```

* `<urn:uuid:5b3359b7-9340-427e-beaf-f06b9b176d52>` <https://www.gshome.sk/pozicky-vozokany>

  ```
  regionálne noviny nájdeš, čo hľadáš GALANTSKO
  Hlavná 45, Vozokany 0917 433 32936-0049 0948 041 103, www.uni-decor.eu, Kráľová n./V. 694 Výroba vitrážneho skla Tiffany Ólomüvegezés Gravírovanie a maľovanie nápisov na sklo Üveggravírozás 36-0018 Okná a dvere plastové, drevené
  Reality Plavé Vozokany - Reality Levice
  Ponúkame na predaj rekonštruovaný RD v obci Plavé Vozokany okres Levice zastavaná plocha 691m2 ,záhrada 164m2 .RD má-3 izby ,kuchyňu WC , kúpeľňu, špajzu, celý… Dražba rodinného domu, Plavé…
  požička blažice -
  Aj bez potvrdenia o príjme. Online pôžičku môžete získať aj bez potvrdenia o príjme.
  Stavebné práce -
  Vytvorte optimálnu prezentáciu aj pre ľudí, aj pre vyhľadávače. Firmy v se
  ```

## G11: parked_domain_placeholder_pages

**Members (1).** A large group can mix related but distinct claims; if so, add a row per finding id to `decisions.csv` instead of one row for the group.

* `parked_domain_placeholder_pages` (baseline:highdup, 2 docs): Some documents are not real content pages at all but auto-generated 'this domain has no website yet' / hosting-registrar placeholder pages (typically from Websupport.sk-style templates), which contain  
  `text LIKE '%K tejto doméne zatiaľ neexistuje žiadny webhosting%' OR text LIKE '%Na tejto%doméne zatiaľ%nič nie je%' OR text LIKE '%doména je parkovaná`

**Description.** Some documents are not real content pages at all but auto-generated 'this domain has no website yet' / hosting-registrar placeholder pages (typically from Websupport.sk-style templates), which contain no topical content and are near-identical to each other across many different domains.

**Selector.** `text LIKE '%K tejto doméne zatiaľ neexistuje žiadny webhosting%' OR text LIKE '%Na tejto%doméne zatiaľ%nič nie je%' OR text LIKE '%doména je parkovaná%' OR text LIKE '%Websupport.sk ponúka najnižšie ceny domén%'`

**Prevalence.** 2 of 2,034,896 (0.0001%), measured on the 1-in-13 text sample.

**Overlap with the obvious static slices.** LID-Disagree 50%, LowConf 0%, HighDup 100%

**Auditor's own precision estimate.** 0.85

**Auditor's stated likely false positives.** Legitimate pages that happen to mention a registrar in passing without being a parked-domain placeholder themselves; low-recall pattern so precision should stay high.

**Fresh examples the auditor never saw:**

* `<urn:uuid:884a4503-1c3e-4899-bdd1-2affb13ffdce>` <http://4init.sk/>

  ```
  Na tejto
  doméne zatiaľ
  nič nie je
  Dôvodov, prečo sa nezobrazuje žiadny obsah, môže byť
  viacero. Ak ste správca webu, môžete nahrať/zmazať
  existujúci obsah alebo kontaktovať svojho webadmina.
  S nahraním obsahu vám pomôže tento návod.
  Overte si novú doménu vo Websupporte
  Nothing to see
  here yet
  There might be several reasons why no content is displayed. If
  you're the web admin, you can upload/delete the existing content,
  and if not, you can contact them.
  This guide can help you upload the content.
  ```

* `<urn:uuid:016ae022-ffab-49eb-8096-c82c72ecec40>` <http://agrobiochemix.pl/>

  ```
  K tejto doméne zatiaľ neexistuje žiadny webhosting
  Websupport.sk ponúka najnižšie ceny domén na slovenskom trhu. Slovenské domény je možné registrovať dlhodobo len za 10,90 eur.
  Vyberte si webhosting na WebSupport.sk
  Doménu prvej úrovne môžete získať jednoducho, stači si overiť, či je voľná a o zvyšok sa postará Websupport.sk. Okrem slovenských domén môžete registrovať ďalších 40 zahraničných alebo svetových domén vrátane .info, .com, .eu.
  ```
