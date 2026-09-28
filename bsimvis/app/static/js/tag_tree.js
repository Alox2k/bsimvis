// Shared hierarchy-tree builder over tag ids -- one code path for every view
// that draws a TagColor-based axis tree (file view's function tag tree and
// file tag tree, bin-sim's pairwise function tag tree). Axis discovery and
// the nesting rule live here once so the trees cannot drift apart the way
// file_view's and bin-sim's copies already had before this existed.
const TagTree = (() => {
    // Every axis a set of tag ids carries mass on, sorted. '' ("all axes") is
    // not included here -- a caller adds it to the picker itself, since only
    // some pickers want it offered.
    function axes(tagIds) {
        const set = new Set();
        (tagIds || []).forEach(t => set.add(TagColor.axisOf(t)));
        return [...set].sort();
    }

    const SEVERITY_ORDER = ['high', 'medium', 'low', 'none'];
    function severityRank(node) {
        const i = SEVERITY_ORDER.indexOf(node.label);
        return i === -1 ? SEVERITY_ORDER.length : i;
    }

    // entries: [[tagId, count], ...]. axis === '' means unfiltered: the top
    // level of the trie is the axis name itself, so every namespace a tag set
    // carries shows up as its own group, with that axis's usual chain nested
    // underneath exactly as a single-axis tree would draw it.
    function build(entries, axis) {
        const root = { children: new Map() };
        (entries || []).forEach(([tagId, count]) => {
            const a = TagColor.axisOf(tagId);
            if (axis && a !== axis) return;
            let node = root;
            const chain = axis ? TagColor.chain(tagId) : [a, ...TagColor.chain(tagId)];
            chain.forEach(prefix => {
                let next = node.children.get(prefix);
                if (!next) {
                    const isAxisHead = !axis && prefix === a;
                    const segs = isAxisHead ? [] : TagColor.levels(prefix).segs;
                    next = {
                        id: prefix, prefix,
                        label: isAxisHead ? a : (segs[segs.length - 1] || prefix),
                        axisHead: isAxisHead,
                        count: 0, children: new Map(), tagIds: [],
                    };
                    node.children.set(prefix, next);
                }
                next.count += count;
                // The original id(s) that reached this node -- a leaf's own id
                // (`groupId`) has its detail tail stripped, so a caller that
                // needs the exact stored tag (a provenance lookup, a full-text
                // display) reads it from here rather than from `id`.
                next.tagIds.push(tagId);
                node = next;
            });
        });

        // axisCtx: the axis governing sort order at this node's children --
        // severity is ordinal, everything else sorts by mass.
        const finish = (node, axisCtx) => {
            const kids = [...node.children.values()]
                .map(k => finish(k, k.axisHead ? k.id : axisCtx));
            kids.sort(axisCtx === 'severity'
                ? (x, y) => severityRank(x) - severityRank(y)
                : (x, y) => y.count - x.count);
            node.children = kids;
            return node;
        };
        let nodes = finish(root, axis).children;
        // A single-axis tree's picker already names the namespace, so a lone
        // top node just repeats it -- fold it away. Not done in "all axes"
        // mode: there the top nodes *are* the namespace labels.
        if (axis && nodes.length === 1 && nodes[0].children.length) nodes = nodes[0].children;
        return nodes;
    }

    return { axes, build };
})();

window.TagTree = TagTree;
