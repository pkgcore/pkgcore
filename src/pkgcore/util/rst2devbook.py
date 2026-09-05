"""A docutils's writer for DevBook format [#]_

.. [#] https://devmanual.gentoo.org/appendices/devbook-guide/index.html
"""

from docutils import nodes, writers
from lxml import etree


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
    def _is_compact_list_item(node: nodes.Node) -> bool:
        if not isinstance(item := node.parent, nodes.list_item):
            return False
        return all(
            len(x.children) == 1 and isinstance(x.children[0], nodes.paragraph)
            for x in item.parent.children
        )

    def visit_paragraph(self, node):
        if self._is_compact_list_item(node):
            return
        self._push_element("p")

    def depart_paragraph(self, node):
        if self._is_compact_list_item(node):
            return
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

    def visit_title(self, node):
        self._push_element("title")

    def depart_title(self, node):
        self._pop_element()
        if self.section_depth > 0:
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
        if self.estack[-1].tag == "body":
            self._pop_element()
        self._pop_element()

    def visit_warning(self, node):
        self._push_element("warning")
        self.tb.data("\n\n".join(child.astext() for child in node.children))
        self._pop_element()
        raise nodes.SkipNode

    def depart_warning(self, node):
        pass

    def visit_title_reference(self, node):
        pass

    def depart_title_reference(self, node):
        pass

    def visit_reference(self, node):
        internal_ref = False

        # internal ref style #1: it declares itself internal
        if node.hasattr("internal"):
            internal_ref = node["internal"]

        # internal ref style #2: it hides as an external ref, with strange
        # qualities.
        if (
            node.hasattr("anonymous")
            and (node["anonymous"] == 1)
            and node.hasattr("refuri")
            and (node["refuri"][0] == "_")
        ):
            internal_ref = True
            node["refuri"] = node["refuri"][1:]

        assert not internal_ref

        if node.hasattr("refid"):
            assert False
            self._push_element("link", {"linkend": node["refid"]})
        elif node.hasattr("refuri"):
            if internal_ref:
                pass
                # ref_name = os.path.splitext(node['refuri'])[0]
                # self._push_element('link', {'linkend': ref_name})
            else:
                self._push_element("uri", link=node["refuri"])
        else:
            assert False

    def depart_reference(self, node):
        if node.hasattr("refid") or node.hasattr("refuri"):
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
