"""Conservative sentence-local rules. Rejections are candidates for human review."""
from dataclasses import dataclass
import json
import re

import spacy
from spacy.matcher import Matcher, PhraseMatcher

from src.collect.common import REPO_ROOT

RULE_VERSION = "1.0.0"
RULE_IDS = ("a4-task-title", "a4-task-current", "a4-dataset-evaluate", "a4-dataset-experiments")
METHOD_RULE_IDS = ("b5-method-title", "b5-method-use", "b5-method-based")


@dataclass(frozen=True)
class Candidate:
    entity_id: str
    start: int
    end: int
    rule_id: str | None
    reason: str | None


class Extractor:
    def __init__(self, dictionary=None, model="auto"):
        self.dictionary = dictionary or json.loads((REPO_ROOT / "config/a4_dictionary.json").read_text(encoding="utf-8"))
        if model == "auto":
            model = "en_core_web_sm" if spacy.util.is_package("en_core_web_sm") else "blank"
        self.nlp = spacy.blank("en") if model == "blank" else spacy.load(model)
        # English suffix defaults can retain the full stop in names such as
        # ImageNet-21K.; split it without changing the source text/offsets.
        self.nlp.tokenizer.suffix_search = spacy.util.compile_suffix_regex(
            [*self.nlp.Defaults.suffixes, r"(?<=[A-Za-z0-9])\."]).search
        # The same explicit sentence policy is used with either tokenizer. No parser/NER needed.
        for pipe in list(self.nlp.pipe_names):
            self.nlp.remove_pipe(pipe)
        self.nlp.add_pipe("sentencizer")
        self.runtime = f"spacy-{spacy.__version__}:{model}-{self.nlp.meta.get('version', '0.0.0')}:sentencizer-1"
        self.model = model
        self.entities = {}
        self.phrases = PhraseMatcher(self.nlp.vocab, attr="LOWER", validate=True)
        aliases = {}
        for group, label in (("tasks", "Task"), ("datasets", "Dataset"), ("methods", "Method")):
            for item in self.dictionary.get(group, []):
                item = {**item, "label": label}
                if not re.fullmatch(label.lower() + r":[a-z0-9]+(?:-[a-z0-9]+)*", item["id"]):
                    raise ValueError("Invalid dictionary ID: " + item["id"])
                if item["id"] in self.entities:
                    raise ValueError("Duplicate dictionary ID")
                self.entities[item["id"]] = item
                for alias in item["aliases"]:
                    key = tuple(t.lower_ for t in self.nlp.make_doc(alias))
                    if key in aliases and aliases[key] != item["id"]:
                        raise ValueError("Ambiguous dictionary alias: " + alias)
                    aliases[key] = item["id"]
                self.phrases.add(item["id"], [self.nlp.make_doc(a) for a in item["aliases"]])
        self.context = Matcher(self.nlp.vocab, validate=True)
        words = lambda items: {"LOWER": {"IN": items.split()}}
        subjects = [[{"LOWER": "we"}], [words("our this"), words("work paper study method approach model framework")]]
        for name, verbs in (
            ("task", "address addresses tackle study studies investigate solve focus focuses propose present introduce develop"),
            ("eval", "evaluate evaluated test tested benchmark benchmarked assess assessed"),
            ("use", "use uses used using employ employs adopt adopts leverage leverages utilize utilizes exploit exploits apply applies incorporate incorporates build builds built based integrate integrates harness harnesses"),
            ("result", "achieve achieves outperform outperforms obtain obtains demonstrate demonstrates show shows"),
        ):
            variants = sorted({v for v in verbs.split()} | {v + "s" for v in verbs.split()})
            self.context.add(name, [s + [{"LOWER": {"IN": ["is", "are", "has", "been", "also", "extensively", "empirically", "thoroughly"]}, "OP": "{0,3}"},
                                         {"LOWER": {"IN": variants}}] for s in subjects])
        self.context.add("experiments", [[words("our extensive comprehensive quantitative additional experimental"),
                                           words("experiments evaluations results evaluation")],
                                          [words("experiments evaluations results"), {"LOWER": "on"}]])

    def candidates(self, text, field):
        doc = self.nlp(text)
        matches = sorted(set(self.phrases(doc)), key=lambda m: (-(m[2] - m[1]), m[1], m[0]))
        occupied, selected = set(), []
        for match_id, start, end in matches:
            if occupied.intersection(range(start, end)):
                continue
            occupied.update(range(start, end))
            selected.append((self.nlp.vocab.strings[match_id], start, end))
        for entity_id, start, end in sorted(selected, key=lambda m: (m[1], m[2], m[0])):
            mention, entity = doc[start:end], self.entities[entity_id]
            sent = mention.sent
            rule, reason = self.decide(sent, mention, entity, field)
            yield Candidate(entity_id, sent.start_char, sent.end_char, rule, reason)

    def decide(self, sent, mention, entity, field):
        if field not in ("title", "abstract"):
            return None, "unsupported_section"
        low = sent.text.lower()
        tokens = {t.lower_ for t in sent}
        exact = entity.get("case_sensitive_aliases", [])
        if any(mention.text.lower() == a.lower() for a in exact) and mention.text not in exact:
            return None, "ambiguous_alias_case"
        if entity["label"] == "Dataset":
            # Do not match a family inside a different compound: Tiny-ImageNet,
            # COCO-Stuff, ImageNet-C and CIFAR10-LT are separate benchmarks.
            source = sent.doc.text
            before = source[mention.start_char - 1:mention.start_char] if mention.start_char else ""
            after = source[mention.end_char:mention.end_char + 1]
            if before in ("-", "–", "_") or after in ("-", "–", "_"):
                return None, "unmapped_dataset_version_or_subset"
        # Deliberately abstain for mixed claims too: do not transfer a baseline/pretrain role.
        if tokens & {"not", "n't", "never", "neither", "without", "cannot", "unable", "no"}:
            return None, "negated_or_mixed_claim"
        if tokens & {"may", "might", "could", "would", "will", "plan", "future", "potential", "whether"} or "?" in low:
            return None, "hypothetical_or_question"
        if re.search(r"\b(previous|prior|earlier|existing|related work|baseline|baselines|survey|surveys|review|reviews|et al|their|they|others)\b", low):
            return None, "prior_work_or_baseline"
        if entity["label"] != "Method" and re.search(r"\b(pre[- ]?train\w*|training|train|trained|fine[- ]?tun\w*)\b", low):
            return None, "training_or_mixed_roles"
        if re.search(r"\b(for example|such as|e\.g\.|applications? (?:include|including|in|like)|can be (?:used|applied))\b", low):
            return None, "application_example"
        if entity["label"] == "Method":
            if field == "title":
                return "b5-method-title", None
            local = sent.as_doc()
            cues = [(self.nlp.vocab.strings[mid], s + sent.start, e + sent.start) for mid, s, e in self.context(local)]
            if any(kind == "use" and 0 <= mention.start - end <= 12 for kind, start, end in cues):
                return "b5-method-use", None
            after = [t.lower_ for t in sent.doc[mention.end:mention.end + 2]]
            if after[:1] == ["based"] or (after[:1] == ["-"] and after[1:2] in (["based"], ["driven"], ["guided"])):
                if tokens & {"we", "our"}:
                    return "b5-method-based", None
            return None, "no_current_method_claim"
        if entity["label"] == "Task" and field == "title":
            return "a4-task-title", None
        if entity["label"] == "Dataset" and field != "abstract":
            return None, "dataset_requires_evaluation_sentence"
        if entity["label"] == "Dataset" and (";" in low or re.search(r"\b(?:but|whereas)\b", low)):
            return None, "mixed_clause_roles"
        local = sent.as_doc()
        cues = [(self.nlp.vocab.strings[mid], s + sent.start, e + sent.start) for mid, s, e in self.context(local)]
        if entity["label"] == "Task":
            if any(kind == "task" and 0 <= mention.start - end <= 18 for kind, start, end in cues):
                return "a4-task-current", None
            return None, "no_current_task_claim"
        # A known generic alias followed by an unknown version/subset must not be collapsed.
        tail = sent.doc[mention.end:min(mention.end + 3, sent.end)].text
        if re.match(r"\s*(?:[-–]\s*)?(?:v\d|\d|val\d|test\d|mini\b)", tail, re.I):
            return None, "unmapped_dataset_version_or_subset"
        prepositions = {"on", "using", "over", "across"}
        result_words = {"show", "shows", "demonstrate", "demonstrates", "reveal", "reveals", "confirm", "confirms", "validate", "validates"}
        for kind, start, end in cues:
            gap = sent.doc[end:mention.start]
            if kind == "eval" and 0 <= mention.start - end <= 18 and ({t.lower_ for t in gap} & prepositions):
                if any(t.lower_ in {"collect", "download", "describe", "introduce", "release", "mention", "discuss", "use"} for t in gap):
                    continue
                prep = next(i for i, t in enumerate(gap) if t.lower_ in prepositions)
                obj = gap[:prep]
                if sent.doc[start].lower_ == "we" and len(obj) and not any(t.lower_ in {"our", "proposed", "this"} for t in obj):
                    continue
                return "a4-dataset-evaluate", None
            if kind == "experiments" and 0 <= mention.start - start <= 18 and tokens & result_words:
                if {t.lower_ for t in sent.doc[start:mention.start]} & prepositions:
                    return "a4-dataset-experiments", None
            if kind == "result" and abs(mention.start - end) <= 22:
                # Explicit current-model result, with the dataset introduced by 'on'.
                before = sent.doc[max(sent.start, mention.start - 3):mention.start]
                if any(t.lower_ == "on" for t in before):
                    return "a4-dataset-evaluate", None
        return None, "no_current_evaluation_claim"
