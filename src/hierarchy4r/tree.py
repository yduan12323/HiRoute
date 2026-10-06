"""Static artifact validation, independent of all query states."""
import hashlib
import json


def tree_bytes(tree):
    return (json.dumps(tree,sort_keys=True,separators=(',',':'))+'\n').encode()


def tree_hash(tree):
    return hashlib.sha256(tree_bytes(tree)).hexdigest()


def validate_tree(tree):
    nodes = tree['regions']
    all_ids = set(range(len(tree['site_ids'])))
    assert len(set(tree['site_ids'])) == len(all_ids)
    assert set(nodes[0]['members']) == all_ids
    leaves = []
    for i,n in enumerate(nodes):
        assert len(set(n['members'])) == len(n['members'])
        if n['children']:
            assert len(n['children']) == 2
            a,b = [nodes[c] for c in n['children']]
            assert all(nodes[c]['parent'] == i for c in n['children'])
            assert set(a['members']).isdisjoint(b['members'])
            assert set(a['members']) | set(b['members']) == set(n['members'])
        else:
            leaves.extend(n['members'])
    assert len(leaves) == len(all_ids) and set(leaves) == all_ids
    return True
