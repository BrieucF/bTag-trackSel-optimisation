import ROOT
from array import array
import os
import sys 

def gt(l, r): return l > r
def geq(l, r): return l >= r
def lt(l, r): return l < r
def leq(l, r): return l <= r
def eq(l, r): return l == r
def neq(l, r): return l != r

class trackCutSelector:
    def __init__(self, cuts):
        self.cuts = cuts

    def evaluate(self, tree, trackN):
        for cut in self.cuts:
            value = tree.__getattr__(cut[0])[trackN]
            if not cut[1]( value, cut[2] ):
                return False
        return True

class trackMVASelector:
    def __init__(self, path, name, cut, trackVars):
        self.name = name
        self.path = path
        self.cut = cut
        self.reader = ROOT.TMVA.Reader()
        # We cannot use a dict to hold the variables since TMVA cares about the order of the variables
        self.trackVars = [ (name, array("f", [0])) for name in trackVars ]
        for var in self.trackVars:
            self.reader.AddVariable(var[0], var[1])
        self.reader.BookMVA(self.name, self.path)

    def sync(self, tree, trackN):
        for var in self.trackVars:
            var[1][0] = tree.__getattr__(var[0])[trackN]

    def getValue(self, tree, trackN):
        self.sync(tree, trackN)
        return self.reader.EvaluateMVA(self.name)

    def evaluate(self, tree, trackN):
        return self.getValue(tree, trackN) > self.cut



def produceTaggedJetTree(rootFiles, treeDirectory, outFileName, trackCut=None, trackMVA=None):

    tree = ROOT.TChain(treeDirectory)
    for file in rootFiles:
        if not os.path.isfile(file):
            print "Error: file {} does not exist.".format(file)
            sys.exit(1)
        tree.Add(file)

    outFile = ROOT.TFile(outFileName, "recreate")
    outTree = ROOT.TTree("jetTree", "jetTree")

    # The variables that are simply copied from the input tree
    copiedVariablesToStore = ["Jet_genpt", "Jet_pt", "Jet_ntracks", "Jet_eta", "Jet_phi", "Jet_flavour"]
    copiedVariables = { name: array("d", [0]) for name in copiedVariablesToStore }

    # The variables that we compute here and store in the output tree
    outVariablesToStore = ["Jet_nseltracks", "Jet_Ip", "TCHE", "TCHP"]
    outVariables = { name: array("d", [0]) for name in outVariablesToStore }
    
    for name, var in copiedVariables.items() + outVariables.items():
        outTree.Branch(name, var, name + "/D")

    # Create a trackCutSelector to select tracks using cuts
    myTrackCutSel = None
    if trackCut is not None:
        myTrackCutSel = trackCutSelector(trackCut)

    # Create a trackMVASelector to select tracks using the MVA output
    myTrackMVASel = None
    if trackMVA is not None:
        if not os.path.isfile(trackMVA["path"]):
            print "Error: file {} does not exist.".format(trackMVA["path"])
            sys.exit(1)
        myTrackMVASel = trackMVASelector(trackMVA["path"], trackMVA["name"], trackMVA["cut"], trackMVA["vars"])

    nEntries = tree.GetEntries()
    print "Will loop over ", nEntries, " events."
    
    # Looping over events
    for entry in xrange(nEntries):
        if (entry+1) % 1000 == 0:
            print "Event {}.".format(entry+1)
        tree.GetEntry(entry)

        # Looping over jets
        for jetInd in xrange(tree.nJet):

            selTracks = []

            # Looping over tracks
            for track in xrange(tree.Jet_nFirstTrack[jetInd], tree.Jet_nLastTrack[jetInd]):
                keepTrack = True

                if myTrackCutSel is not None:
                    keepTrack = keepTrack and myTrackCutSel.evaluate(tree, track)
                if not keepTrack: continue

                if myTrackMVASel is not None:
                    keepTrack = keepTrack and myTrackMVASel.evaluate(tree, track)
                if not keepTrack: continue

                # For selected tracks, store pair (track number, IPsig)
                selTracks.append( (track, tree.__getattr__("Track_IPsig")[track]) )

            if len(selTracks) == 0: continue

            outVariables["Jet_nseltracks"][0] = len(selTracks)

            # Sort tracks according to decreasing IP significance
            sorted(selTracks, reverse = True, key = lambda track: track[1])

            # TCHE = IPsig of 2nd track, TCHP = IPsig of 3rd track (default to -10**10)
            outVariables["Jet_Ip"][0] = selTracks[0][1]
            outVariables["TCHE"][0] = -10**10
            outVariables["TCHP"][0] = -10**10
            if len(selTracks) > 1:
                outVariables["TCHE"][0] = selTracks[1][1]
            if len(selTracks) > 2:
                outVariables["TCHP"][0] = selTracks[2][1]

            # Get value of the variables we simply copy
            for name, var in copiedVariables.items():
                var[0] = tree.__getattr__(name)[jetInd]

            outTree.Fill()

    outFile.cd()
    outTree.Write()
    outFile.Close()
