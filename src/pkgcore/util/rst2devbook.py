"""A docutils's writer for DevBook format [#]_

.. [#] https://devmanual.gentoo.org/appendices/devbook-guide/index.html
"""

from docutils import nodes, writers
from lxml import etree
from snakeoil.klass import alias_method

# docutils admonitions DevBook can express, mapped onto its elements below
_ADMONITIONS = frozenset(
    (
        "note",
        "tip",
        "hint",
        "important",
        "attention",
        "caution",
        "warning",
        "danger",
        "error",
    )
)


class DevBookWriter(writers.Writer):
    """A docutils writer for DevBook."""

    def __init__(self, eclass):
        """Initialize the writer. Takes the root element of the resulting
        DocBook output as its sole argument."""
        super().__init__()
        self.eclass = eclass

    def translate(self):
        """Call the translator to translate the document"""
        self.visitor = DevBookTranslator(self.document, self.eclass)
        self.document.walkabout(self.visitor)
        self.output = self.visitor.astext()


class DevBookTranslator(nodes.NodeVisitor):
    """A docutils translator for DevBook."""

    sections_tags = ("section", "subsection", "subsubsection")

    def __init__(self, document: nodes.document, eclass: str):
        super().__init__(document)
        self.eclass = eclass

        self.estack = []
        self.tb = etree.TreeBuilder()
        self.section_depth = 0

    def astext(self) -> str:
        doc = self.tb.close()
        et = etree.ElementTree(doc)
        return etree.tostring(
            et, encoding="utf-8", xml_declaration=True, pretty_print=True
        ).decode()

    def _push_element(self, name: str, **kwargs):
        e = self.tb.start(name, kwargs)
        self.estack.append(e)
        return e

    def _pop_element(self):
        e = self.estack.pop()
        return self.tb.end(e.tag)

    def visit_document(self, node):
        self.tb.start("devbook", {"self": f"eclass-reference/{self.eclass}/"})
        self.tb.start("chapter", {})

    def depart_document(self, node):
        self.tb.end("chapter")
        self.tb.end("devbook")

    def visit_Text(self, node):
        self.tb.data(str(node).replace("\x00", ""))

    def depart_Text(self, node):
        pass

    @staticmethod
    def _is_bare_paragraph(node: nodes.Node) -> bool:
        """Whether a paragraph's content goes straight into its parent."""
        match parent := node.parent:
            case nodes.list_item():
                # DevBook has no compact list, so a `p` breaks up the item.  Every item has to agree,
                # or they'd be spaced unevenly.
                return all(
                    len(x.children) == 1 and isinstance(x.children[0], nodes.paragraph)
                    for x in parent.parent.children
                )
            case nodes.entry():
                # `th` takes inline content only; in `ti` a lone paragraph would just add a break
                return isinstance(parent.parent.parent, nodes.thead) or (
                    len(parent.children) == 1
                )
        return parent.tagname in _ADMONITIONS

    def visit_paragraph(self, node):
        if not self._is_bare_paragraph(node):
            self._push_element("p")
        elif node is not node.parent.children[0]:
            # keep consecutive paragraphs from running together
            self.tb.data("\n\n")

    def depart_paragraph(self, node):
        if not self._is_bare_paragraph(node):
            self._pop_element()

    def visit_attribution(self, node):
        self._push_element("p")

    def depart_attribution(self, node):
        self._pop_element()

    def visit_literal_block(self, node):
        self._push_element("codesample", lang="ebuild")

    def depart_literal_block(self, node):
        self._pop_element()

    def visit_literal(self, node):
        self._push_element("c")

    def depart_literal(self, node):
        self._pop_element()

    def visit_emphasis(self, node):
        self._push_element("e")

    def depart_emphasis(self, node):
        self._pop_element()

    def visit_strong(self, node):
        self._push_element("b")

    def depart_strong(self, node):
        self._pop_element()

    @staticmethod
    def _is_preformattable(node: nodes.Node) -> bool:
        """Whether a block quote can be rendered as `pre`, which holds bare text."""
        return all(
            isinstance(child, nodes.paragraph)
            and all(isinstance(x, nodes.Text) for x in child.children)
            for child in node.children
        )

    def visit_block_quote(self, node):
        # A reST block quote is just indented content, and DevBook has no element
        # for that; `pre` is the closest, but it holds text and nothing else, so
        # only a quote that is plain paragraphs can go in one.  Anything richer --
        # a list, a definition list, a nested quote, inline markup -- is emitted
        # into the enclosing block instead, unindented but intact.
        if not self._is_preformattable(node):
            return
        self._push_element("pre")
        self.tb.data("\n\n".join(child.astext() for child in node.children))
        self._pop_element()
        raise nodes.SkipNode

    def depart_block_quote(self, node):
        pass

    @staticmethod
    def _is_section_title(node: nodes.Node) -> bool:
        """Whether a title names a chapter or section, as DevBook's does."""
        return isinstance(node.parent, nodes.section | nodes.document)

    def visit_title(self, node):
        if isinstance(node.parent, nodes.table):
            raise nodes.SkipNode  # already taken as the table's caption
        if not self._is_section_title(node):
            # a topic, sidebar or generic admonition heading
            self._push_element("p")
            self._push_element("b")
            return
        self._push_element("title")

    def depart_title(self, node):
        self._pop_element()
        if not self._is_section_title(node):
            self._pop_element()
        elif self.section_depth > 0:
            self._push_element("body")

    def visit_section(self, node):
        if "system-messages" in node["classes"]:
            # docutils' own trailing diagnostics section; see the diagnostics
            # block below.  Its content is dropped there, which would leave an
            # empty `body`, and `body` must hold at least one element.
            raise nodes.SkipNode
        if self.estack and self.estack[-1].tag == "body":
            self._pop_element()
        self._push_element(self.sections_tags[self.section_depth])
        self.section_depth += 1

    def depart_section(self, node):
        self.section_depth -= 1
        body = None
        if self.estack[-1].tag == "body":
            body = self._pop_element()
        section = self._pop_element()
        # a section whose content was all unrenderable -- comments, foreign
        # markup -- would leave an empty `body`, and `body` holds at least one
        # element, so drop the section along with it
        if body is not None and not len(body) and not (body.text or "").strip():
            section.getparent().remove(section)

    #
    # Admonitions.  docutils has more flavors than DevBook, so each maps onto
    # the DevBook element carrying the same weight.
    #

    def visit_note(self, node):
        self._push_element("note")

    def depart_note(self, node):
        self._pop_element()

    visit_tip = alias_method("visit_note")
    depart_tip = alias_method("depart_note")
    visit_hint = alias_method("visit_note")
    depart_hint = alias_method("depart_note")

    def visit_important(self, node):
        self._push_element("important")

    def depart_important(self, node):
        self._pop_element()

    visit_attention = alias_method("visit_important")
    depart_attention = alias_method("depart_important")
    visit_caution = alias_method("visit_important")
    depart_caution = alias_method("depart_important")

    def visit_warning(self, node):
        self._push_element("warning")

    def depart_warning(self, node):
        self._pop_element()

    visit_danger = alias_method("visit_warning")
    depart_danger = alias_method("depart_warning")
    visit_error = alias_method("visit_warning")
    depart_error = alias_method("depart_warning")

    #
    # Tables
    #

    def visit_table(self, node):
        # docutils keeps the caption in a `title` child, DevBook in an
        # attribute, so it has to be read before the element is opened
        caption = [x.astext() for x in node.children if isinstance(x, nodes.title)]
        self._push_element("table", **({"caption": caption[0]} if caption else {}))

    def depart_table(self, node):
        self._pop_element()

    def visit_row(self, node):
        self._push_element("tr")

    def depart_row(self, node):
        self._pop_element()

    def visit_entry(self, node):
        self._push_element(
            "th" if isinstance(node.parent.parent, nodes.thead) else "ti"
        )

    def depart_entry(self, node):
        self._pop_element()

    # DevBook tables have no column specs, and mark header cells individually
    # rather than grouping the rows
    def visit_colspec(self, node):
        raise nodes.SkipNode

    def visit_tgroup(self, node):
        pass

    def depart_tgroup(self, node):
        pass

    def visit_thead(self, node):
        pass

    def depart_thead(self, node):
        pass

    def visit_tbody(self, node):
        pass

    def depart_tbody(self, node):
        pass

    #
    # Field lists, which are definition lists by another name
    #

    def visit_field_list(self, node):
        self._push_element("dl")

    def depart_field_list(self, node):
        self._pop_element()

    def visit_field(self, node):
        pass

    def depart_field(self, node):
        pass

    def visit_field_name(self, node):
        self._push_element("dt")

    def depart_field_name(self, node):
        self._pop_element()

    def visit_field_body(self, node):
        self._push_element("dd")

    def depart_field_body(self, node):
        self._pop_element()

    def visit_doctest_block(self, node):
        self._push_element("pre")
        self.tb.data(node.astext())
        self._pop_element()
        raise nodes.SkipNode

    def visit_rubric(self, node):
        self._push_element("p")
        self._push_element("b")

    def depart_rubric(self, node):
        self._pop_element()
        self._pop_element()

    ### nodes carrying no rendered content
    #
    # Left to the fallback below these would leak their text -- a comment's
    # prose, a substitution's replacement, foreign markup -- into the docs.

    def visit_comment(self, node):
        raise nodes.SkipNode

    def visit_substitution_definition(self, node):
        raise nodes.SkipNode

    def visit_raw(self, node):
        raise nodes.SkipNode

    def unknown_visit(self, node):
        """Render a node DevBook has no element for, rather than failing.

        eclassdoc prose is written by hand, and one eclass reaching for reST
        that doesn't map onto DevBook shouldn't cost the whole run.  A node
        holding blocks of its own gives way to them; a leaf's text needs a `p`
        to live in, since `body` holds block elements only.
        """
        if isinstance(node, nodes.Inline):
            return
        if any(isinstance(x, nodes.Body) for x in node.children):
            return
        if text := node.astext():
            self._push_element("p")
            self.tb.data(text)
            self._pop_element()
        raise nodes.SkipNode

    def unknown_departure(self, node):
        pass

    def visit_title_reference(self, node):
        pass

    def depart_title_reference(self, node):
        pass

    @staticmethod
    def _reference_uri(node: nodes.reference) -> str | None:
        """The URI to link to, or None for a reference DevBook can't express."""
        uri = node.get("refuri")
        # an internal reference wearing an external one's clothes
        if uri and node.get("anonymous") and uri.startswith("_"):
            return None
        return uri

    def visit_reference(self, node):
        # DevBook has no element for a reference to elsewhere in the same
        # document, so those render as their text alone
        if uri := self._reference_uri(node):
            self._push_element("uri", link=uri)

    def depart_reference(self, node):
        if self._reference_uri(node):
            self._pop_element()

    def visit_bullet_list(self, node):
        self._push_element("ul")

    def depart_bullet_list(self, node):
        self._pop_element()

    def visit_enumerated_list(self, node):
        self._push_element("ol")

    def depart_enumerated_list(self, node):
        self._pop_element()

    def visit_list_item(self, node):
        self._push_element("li")

    def depart_list_item(self, node):
        self._pop_element()

    def visit_line_block(self, node):
        pass

    def depart_line_block(self, node):
        pass

    def visit_line(self, node):
        self._push_element("p")

    def depart_line(self, node):
        self._pop_element()

    #
    # Definitions list block
    #

    def visit_definition_list(self, node):
        self._push_element("dl")

    def depart_definition_list(self, node):
        self._pop_element()

    def visit_definition_list_item(self, node):
        pass

    def depart_definition_list_item(self, node):
        pass

    def visit_term(self, node):
        self._push_element("dt")

    def depart_term(self, node):
        self._pop_element()

    def visit_definition(self, node):
        self._push_element("dd")

    def depart_definition(self, node):
        self._pop_element()

    ### docutils diagnostics
    #
    # These report that the eclassdoc isn't valid reST, they aren't eclass
    # content, and docutils has already written them to stderr.  Emitting them
    # also can't produce valid DevBook: `warning` is a block element holding
    # inline content, so neither a `warning` within a `p` nor the `p` docutils
    # wraps the message in validates.

    def visit_problematic(self, node):
        """Render markup docutils choked on as the plain text it was written as."""

    def depart_problematic(self, node):
        pass

    def visit_system_message(self, node):
        """Drop the diagnostic docutils attached to a `problematic` node."""
        raise nodes.SkipNode
