'''
Created on Oct 26, 2018

@author: Vlad
'''

import dendropy
from dendropy.utility import bitprocessing
from helpers import sequenceutils

import os
import sys
import random


def loadTree(treePath, nameSpace=None):
    tree = dendropy.Tree.get(path=treePath, schema="newick", preserve_underscores=True)
    if nameSpace is None:
        nameSpace = tree.taxon_namespace
    else:
        tree.migrate_taxon_namespace(nameSpace)

    tree.is_rooted = False
    tree.resolve_polytomies(limit=2)
    tree.collapse_basal_bifurcation()
    tree.update_bipartitions()
    return tree

def writeTree(tree, outputPath):
    resultTreeString = tree.as_string(schema="newick")
    with open(outputPath, "w") as f:
        f.write(resultTreeString[5:]) 

def compareTreesFromDendropy(tr1, tr2):
    return compareDendropyTrees(dendropy.Tree(tr1), dendropy.Tree(tr2))

#courtesy Erin Molloy
def compareTreesFromPath(treePath1, treePath2):
    print("Comparing {} with {}".format(treePath1, treePath2))
    
    tax = dendropy.TaxonNamespace()
    tr1 = dendropy.Tree.get(path=treePath1,
                            schema='newick',
                            rooting='force-unrooted',
                            taxon_namespace=tax,
                            preserve_underscores=True)
    tr2 = dendropy.Tree.get(path=treePath2,
                            schema='newick',
                            rooting='force-unrooted',
                            taxon_namespace=tax,
                            preserve_underscores=True)

    tr1.collapse_basal_bifurcation(set_as_unrooted_tree=True)
    tr2.collapse_basal_bifurcation(set_as_unrooted_tree=True)

    return compareDendropyTrees(tr1, tr2)
    #print("RF distance on %d shared leaves: %d" % (nl, fp + fn))

#courtesy Erin Molloy
def compareDendropyTrees(tr1, tr2):
    from dendropy.calculate.treecompare \
        import false_positives_and_negatives

    lb1 = set([l.taxon.label for l in tr1.leaf_nodes()])
    lb2 = set([l.taxon.label for l in tr2.leaf_nodes()])
    
    print("Comparing trees with {}|{} and {}|{} leaves..".format(len(lb1), len(tr1.leaf_nodes()), len(lb2), len(tr2.leaf_nodes())))
    
    com = lb1.intersection(lb2)
    if com != lb1 or com != lb2:
        com = list(com)
        tns = dendropy.TaxonNamespace(com)

        tr1.retain_taxa_with_labels(com)
        tr1.migrate_taxon_namespace(tns)

        tr2.retain_taxa_with_labels(com)
        tr2.migrate_taxon_namespace(tns)
    com = list(com)

    tr1.update_bipartitions()
    tr2.update_bipartitions()

    nl = len(com)
    ei1 = len(tr1.internal_edges(exclude_seed_edge=True))
    ei2 = len(tr2.internal_edges(exclude_seed_edge=True))

    [fp, fn] = false_positives_and_negatives(tr1, tr2)
    rf = float(fp + fn) / (ei1 + ei2)

    return (nl, ei1, ei2, fp, fn, rf)

def decomposeGuideTree(subsetsDir, sequencesPath, guideTreePath, maxSubsetSize, maxNumSubsets):
    sequences = sequenceutils.readFromFasta(sequencesPath, removeDashes = False)
    guideTree = loadTree(guideTreePath)
    trees = decomposeTree(guideTree, maxSubsetSize, maxNumSubsets)
    
    taxonSubsets = []
    for tree in trees:
        keep = [n.taxon.label for n in tree.leaf_nodes()]
        taxonSubsets.append(keep)
    
    subsetPaths = []
    for n, subset in enumerate(taxonSubsets):
        subsetPath = os.path.join(subsetsDir, "subset_{}.txt".format(n+1))
        subsetPaths.append(subsetPath)                    
        sequenceutils.writeFasta(sequences, subsetPath, subset) 
    return subsetPaths

def decomposeTree(tree, maxSubsetSize, numSubsets):
    trees = [tree]
    while len(trees) < numSubsets:
        largestTree = max(trees, key=lambda t : len(t.leaf_nodes()))
        
        if maxSubsetSize is not None and len(largestTree.leaf_nodes()) <= maxSubsetSize:
            return trees
        else:
            e = getCentroidEdge(largestTree)
            t1, t2 = bipartitionByEdge(largestTree, e)
            trees.remove(largestTree)
            trees = trees + [t1, t2]
    return trees

def decomposeTreeNumSubsets(tree, numSubsets):
    trees = [tree]
    while len(trees) < numSubsets:
        trees.sort(key=lambda t : len(t.leaf_nodes()), reverse=True)
        e = getCentroidEdge(trees[0])
        t1, t2 = bipartitionByEdge(trees[0], e)
        trees = trees[1:] + [t1, t2]
    return trees

def decomposeTreeMaxSubsetSize(tree, maxSubsetSize, mode = "centroid"):
    numLeaves = len(tree.leaf_nodes())
    if numLeaves > maxSubsetSize:
        if mode == "centroid":
            e = getCentroidEdge(tree)
        elif mode == "random":
            e = getCentroidEdgeRandom(tree, maxSubsetSize/3)

        t1, t2 = bipartitionByEdge(tree, e)
        return decomposeTreeMaxSubsetSize(t1, maxSubsetSize, mode) + decomposeTreeMaxSubsetSize(t2, maxSubsetSize, mode)
    else:
        return [tree]

def bipartitionByEdge(tree, edge):
    newRoot = edge.head_node
    edge.tail_node.remove_child(newRoot)
    newTree = dendropy.Tree(seed_node=newRoot, taxon_namespace = tree.taxon_namespace)
    tree.update_bipartitions()
    newTree.update_bipartitions()
    return tree, newTree

def getCentroidEdge(tree):
    numLeaves = bitprocessing.num_set_bits(tree.seed_node.tree_leafset_bitmask)
    bestBalance = float('inf')
    for edge in tree.postorder_edge_iter():
        if edge.tail_node is None:
            continue
        balance = abs(numLeaves/2 - bitprocessing.num_set_bits(edge.bipartition.leafset_bitmask))
        if balance < bestBalance:
            bestBalance = balance
            bestEdge = edge    
    return bestEdge

def getCentroidEdgeRandom(tree, minBound = 5):
    fullMask = tree.seed_node.tree_leafset_bitmask
    numLeaves = bitprocessing.num_set_bits(fullMask)
    candidates = []
    for edge in tree.postorder_internal_edge_iter():
        if edge.tail_node is None:
            continue
        
        mask = edge.bipartition.leafset_bitmask
        numMask1 = bitprocessing.num_set_bits(mask)
        numMask2 = numLeaves - numMask1
        
        if numMask1 >= minBound and numMask2 >= minBound:
            candidates.append(edge)    
            
    return random.choice(candidates)

