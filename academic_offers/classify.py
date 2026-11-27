"""Rule-based classification into broad field / subfield and career stage.

Fields follow the three ERC domains (plus Social Sciences and Humanities split in two) so the
site reads naturally for international researchers; the original Spanish *área de conocimiento*
is always kept in `area_raw`.

Rules are matched in order against "area + title", so put specific keywords before general ones.
Unmatched offers fall into "Multidisciplinary / other" — the place for a later LLM classifier.
"""
from __future__ import annotations

import re

from .models import Offer

PE, LS, SS, HU = "Physical Sciences & Engineering", "Life & Health Sciences", "Social Sciences", "Humanities"

FIELD_RULES: list[tuple[str, str, str]] = [
    # (regex, field, subfield)
    # Official FCT scientific-domain labels, kept ahead of broad keyword rules.
    (r"ciências agrárias", LS, "Agriculture, Food & Veterinary"),
    (r"ciências da engenharia e tecnologias", PE, "Engineering & Technology"),
    (r"ciências exatas", PE, "Physical & Mathematical Sciences"),
    (r"humanidades", HU, "Humanities"),
    (r"ciências médicas e da saúde", LS, "Health & Medicine"),
    (r"ciências naturais", LS, "Natural Sciences"),
    (r"ciências sociais", SS, "Social Sciences"),
    (r"ciências da vida|ciências biomédicas|ciências da saúde", LS, "Life & Health Sciences"),
    (r"ciências jurídico|direito|law|jur[íi]dic", SS, "Law"),
    (r"ciências do desporto|desporto|sport", SS, "Sports Sciences"),
    (r"ciências empresariais|gestão|management", SS, "Economics & Business"),
    (r"estudos musicais|musicologia|música", HU, "Music"),
    (r"did[áa]ctica|educaci[óo]n f[íi]sica|deport|ensino|pedagogia", SS, "Education"),
    (r"computaci|inteligencia artificial|inform[áa]tic|lenguajes y sistemas|computer|software|data scien|telem[áa]tic|arquitectura y tecnolog[íi]a de computadores", PE, "Computer Science & AI"),
    (r"veterinari|producci[óo]n animal|sanidad animal|medicina y cirug[íi]a animal|anatom[íi]a.*comparadas|agr[íi]col|agronom|edafolog|forestal|tecnolog[íi]a de alimentos|nutrici[óo]n y bromatolog", LS, "Agriculture, Food & Veterinary"),
    (r"fisioterapia|anatom[íi]a|embriolog|otorrino|traumatolog|ortoped|dermatolog|urolog|enfermer|medicina|cirug[íi]a|cardiolog|cardiovascular|cardi|pediatr|psiquiatr|radiolog|farmacolog|farmacia|odontolog|estomatolog|obstetricia|oftalmolog|salud|cl[íi]nic|m[ée]dic|hematol|patolog|inmunolog|nursing", LS, "Health & Medicine"),
    (r"neuro", LS, "Neuroscience"),
    (r"bioqu[íi]mica|biolog[íi]a|gen[ée]tica|microbiolog|fisiolog|bot[áa]nica|zoolog|ecolog|parasitolog|biomed|protein|\bcell|linfocit|biolog[íi]a molecular|biotecnolog", LS, "Biology & Biomedicine"),
    (r"estad[íi]stica|matem[áa]tic|[áa]lgebra|an[áa]lisis matem|geometr|mathemat", PE, "Mathematics & Statistics"),
    (r"qu[íi]mica|chemi|cristalograf", PE, "Chemistry"),
    (r"photon|f[íi]sica|optic|[óo]ptica|quantum|cu[áa]ntic|astronom|astrof[íi]s|electromagnet|fermi|cold atom|nanotub", PE, "Physics & Photonics"),
    (r"geolog|geodin[áa]mica|estratigraf|paleontolog|petrolog|geograf[íi]a f[íi]sica|clim|oceano|medio ambiente|environment|meteorolog", PE, "Earth & Environment"),
    (r"ingenier|minas|m[áa]quinas|motores|naval|aeroesp|tecnolog[íi]a electr[óo]nica|electr[óo]nic|el[ée]ctric|mec[áa]nica|automática|sistemas y autom|estructuras|construcci|arquitect|expresi[óo]n gr[áa]fica|materiales|engineering|energ", PE, "Engineering & Architecture"),
    (r"econ[óo]m|contabilidad|organizaci[óo]n de empresas|comercializaci[óo]n|finan|empresa|business|marketing|m[ée]todos cuantitativos", SS, "Economics & Business"),
    (r"derecho|law|jur[íi]dic", SS, "Law"),
    (r"psicolog|psychol|personalidad, evaluaci", SS, "Psychology"),
    (r"did[áa]ctica|educaci[óo]n|pedagog|teor[íi]a e historia de la educaci|education", SS, "Education"),
    (r"sociolog|ciencia pol[íi]tica|antropolog|trabajo social|geograf[íi]a humana|an[áa]lisis geogr|comunicaci|periodismo|biblioteconom|documentaci", SS, "Sociology, Politics & Communication"),
    (r"filolog|ling[üu][íi]stic|lengua|literatura|traducci|language", HU, "Languages & Literature"),
    (r"historia|\barte\b|arqueolog|m[úu]sica|patrimonio|prehistoria", HU, "History, Art & Archaeology"),
    (r"filosof|[ée]tica|l[óo]gica", HU, "Philosophy"),
]
_COMPILED = [(re.compile(p, re.I), f, s) for p, f, s in FIELD_RULES]

STAGE_RULES: list[tuple[str, str]] = [
    (r"investigadores?\s+dl\s*57|investigador(?:a)?\s+de\s+n[ií]vel\s+(?:inicial|interm[eé]dio)|investigador(?:a)?\s+doutorado", "Researcher / DL 57"),
    (r"catedr[áa]tic|full professor|profesor/a de investigaci|professor catedrático", "Senior faculty / research professor"),
    (r"titular de universidad|permanente laboral|cient[íi]fico/a titular|investigador/a cient|permanent position|group leader|tenure|professor associado|professor auxiliar|investigador principal|investigador auxiliar", "Permanent faculty / researcher"),
    (r"ayudante doctor|ram[óo]n y cajal|tenure.track|erc (starting|consolidator)|consolidator grant|research fellows|icrea", "Tenure-track & independent fellowships"),
    (r"postdoc|post-doc|posdoc|juan de la cierva|postdoctoral|pós[- ]?doutor", "Postdoc"),
    (r"predoc|phd|doctoral|fpu|fpi|doctorado|student research|doutorand|bolsa de doutoramento|doutoramento", "PhD / predoc"),
    (r"t[ée]cnic|technician|manager|gesti[óo]n|ingeniero de|operations|técnico superior", "Technical & research support"),
]
_STAGES = [(re.compile(p, re.I), s) for p, s in STAGE_RULES]


def classify(o: Offer) -> Offer:
    text = f"{o.area_raw} {o.title}"
    for pat, field, sub in _COMPILED:
        if pat.search(text):
            o.field, o.subfield = field, sub
            break
    else:
        o.field, o.subfield = "Multidisciplinary / other", ("Funding calls" if o.kind == "call" else "")

    stage_text = f"{o.position_type} {o.title}"
    o.stage = o.stage or next((s for pat, s in _STAGES if pat.search(stage_text)), "")  # keep a stage the source gave
    if not o.stage:
        o.stage = "Funding call (various stages)" if o.kind == "call" else "Other"
    return o
