#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Feb  6 05:46:38 2019

@author: osboxes
"""
import os
from panda3d.core import LColor, CollisionBox, CollisionNode
from panda3d.core import (
    GeomVertexFormat,
    GeomVertexData,
    GeomVertexWriter,
    Geom,
    GeomLines,
    GeomNode,
)

from Colors import *

verbosityLow = 0
verbosityMedium = 1
verbosityHigh = 2
FILE_VERBOSITY = verbosityHigh  # change this to change printing verbosity of this file

def printLog(txt, verbosity=verbosityLow):
    if FILE_VERBOSITY >= verbosity:
        print(txt)
        
class cCell:
    def __init__(self, column):
        self.active = False
        self.predictive = False
        self.winner = False
        self.presynapticFocus = False
        self.focused = False
        self.correctlyPredicted = False
        self.falselyPredicted = False
        self.transparency = 1.0
        self.column = column  # to be able to track column that this cell belongs to
        self.idx = -1
        self.showPredictionCorrectness = False

    def CreateGfx(
        self, loader, idx
    ):  # idx is neccesary to be able to track it down for mouse picking

        self.idx = idx
        self.__node = loader.loadModel(os.path.join(os.getcwd(),"models/cube"))
        self.__node.setPos(0, 0, 0)
        self.__node.setScale(0.5, 0.5, 0.5)
        self.__node.setTag("clickable", str(idx))  # to be able to click on it
        self.__node.setName("cell")

        # COLLISION
        collBox = CollisionBox(self.__node.getPos(), 1.0, 1.0, 1.0)
        cnodePath = self.__node.attachNewNode(CollisionNode("cnode"))
        cnodePath.node().addSolid(collBox)

        self.UpdateState(False, False, False)

    def UpdateState(self, active, predictive, winner, focused=False, presynapticFocus=False, showPredictionCorrectness = False, prev_predictive = False):

        # determine if previous prediction was correct or not

        if showPredictionCorrectness:#was predicted last step
            if prev_predictive and active:#was predictive and now is active
                self.correctlyPredicted = True
                self.falselyPredicted = False
            elif prev_predictive and not active:
                self.correctlyPredicted = False
                self.falselyPredicted = True
            else:#wasn't predictive previous step, so can't be correct or false
                self.correctlyPredicted = False
                self.falselyPredicted = False
        else: # we don't want to see correctness
            self.correctlyPredicted = False
            self.falselyPredicted = False
            self.showPredictionCorrectness = showPredictionCorrectness # store it for purposes of description

        self.active = active
        self.predictive = predictive
        self.winner = winner
        self.focused = focused

        if self.focused:# if we have this cell focused, modify LOD to long distance
            self.column.LODUpdateSwitch_long()

        self.presynapticFocus = presynapticFocus
        
        if self.focused:
            self.__node.setColor(COL_CELL_FOCUSED)
        elif self.correctlyPredicted:
            col = COL_CELL_CORRECTLY_PREDICTED
            self.__node.setColor(col)
        elif self.falselyPredicted:
            col = COL_CELL_FALSELY_PREDICTED
            self.__node.setColor(col)
        elif self.winner:
            col = COL_CELL_WINNER
            self.__node.setColor(col)
        elif self.predictive and self.active:
            col = COL_CELL_ACTIVE_AND_PREDICTIVE
            self.__node.setColor(col)
        elif self.predictive:
            col = COL_CELL_PREDICTIVE
            self.__node.setColor(col)
        elif self.active:
            col = COL_CELL_ACTIVE
            self.__node.setColor(col)
        elif self.presynapticFocus:
            col = COL_CELL_PRESYNAPTIC_FOCUS
            self.__node.setColor(col)
        else:
            COL_CELL_INACTIVE.setW(self.transparency)
            col = COL_CELL_INACTIVE
            self.__node.setColor(col)

    def setFocus(self):
        self.UpdateState(self.active, self.predictive, self.winner, True)  #no change except focus

    def resetFocus(self):
        self.UpdateState(self.active, self.predictive, self.winner, False)  #reset focus
        self.column.LODUpdateSwitch_normal()

    def setPresynapticFocus(self):
        self.UpdateState(self.active, self.predictive, self.winner, self.focused, True)  # no change except presynaptic focus

    def resetPresynapticFocus(self):
        self.UpdateState(self.active, self.predictive, self.winner, self.focused, False)  # reset presynaptic focus

    def setTransparency(self, transparency):
        self.transparency = transparency

        self.UpdateState(self.active, self.predictive, self.winner, self.focused, self.presynapticFocus)
        
    def updateWireframe(self,value):
        if value:
            self.__node.setRenderModeFilledWireframe(LColor(0,0,0,1.0))
        else:
            self.__node.setRenderModeFilled()
            
    def getNode(self):
        return self.__node
    
    def CreateDistalSynapses(self, HTMObject, layer, data, inputObjects):

        self.DestroyDistalSynapses()

        printLog("Creating distal synapses", verbosityMedium)

        #printLog("EXTERNAL DISTAL:"+str(inputObjects))
        #printLog("HTM inputs:"+str(HTMObject.inputs))
        #printLog("HTM layers:" + str(HTMObject.layers))

        #input object could be either input or layer instance
        for inputObj in inputObjects:
            if inputObj in HTMObject.inputs:
                HTMObject.inputs[inputObj].resetPresynapticFocus()
            elif inputObj in HTMObject.layers:
                HTMObject.layers[inputObj].resetPresynapticFocus()
            else:
                raise SyntaxError("Wrongly defined distal input to the layer! Input name:" + str(inputObj))

        for segment in data:

            for presynCellID in data[segment]:
                
                cellID = presynCellID % layer.nOfCellsPerColumn
                colID = (int)(presynCellID / layer.nOfCellsPerColumn)

                if colID < len(layer.minicolumns):
                    presynCell = layer.minicolumns[colID].cells[cellID] # it is within current layer
                else: # it is for external distal input
                    cellID = presynCellID - len(layer.minicolumns)*layer.nOfCellsPerColumn
                    for inputObj in inputObjects:

                        if inputObj in HTMObject.inputs:
                            if cellID < HTMObject.inputs[inputObj].count:
                                presynCell = HTMObject.inputs[inputObj].inputBits[cellID]
                                break
                            else: # not this one
                                cellID -= HTMObject.inputs[inputObj].count

                        elif inputObj in HTMObject.layers:
                            if cellID < HTMObject.layers[inputObj].nOfCellsPerColumn * len(HTMObject.layers[inputObj].minicolumns):

                                presynCell = HTMObject.layers[inputObj].minicolumns[(int)(cellID / HTMObject.layers[inputObj].nOfCellsPerColumn)].cells[cellID % HTMObject.layers[inputObj].nOfCellsPerColumn]
                                break
                            else: # not this one
                                cellID -= HTMObject.layers[inputObj].nOfCellsPerColumn * len(HTMObject.layers[inputObj].minicolumns)

                presynCell.setPresynapticFocus()  # highlight presynaptic cells
        
                form = GeomVertexFormat.getV3()
                vdata = GeomVertexData("DistalSynapseLine", form, Geom.UHStatic)
                vdata.setNumRows(1)
                vertex = GeomVertexWriter(vdata, "vertex")

                vertex.addData3f(
                    presynCell
                    .getNode()
                    .getPos(self.__node)
                )
                vertex.addData3f(0, 0, 0)
               

                prim = GeomLines(Geom.UHStatic)
                prim.addVertices(0, 1)

                geom = Geom(vdata)
                geom.addPrimitive(prim)

                node = GeomNode("DistalSynapse")
                node.addGeom(geom)
                
                nodePath = self.__node.attachNewNode(node)
                
                nodePath.setRenderModeThickness(2)

                # color of the line
                if presynCell.active:
                    nodePath.setColor(COL_DISTAL_SYNAPSES_ACTIVE)
                else:
                    nodePath.setColor(COL_DISTAL_SYNAPSES_INACTIVE)


    def getDescription(self):
        txt = ""
        txt += "ID:" + str(self.idx) + "  ABS ID:"+ str(len(self.column.cells)*self.column.idx + self.idx) +"\n"
        txt += "Active:" + str(self.active)+"\n"
        txt += "Winner:" + str(self.winner) + "\n"
        txt += "Predictive:" + str(self.predictive)+"\n"
        txt += "Correctly predicted:" + 'N/A' if not self.showPredictionCorrectness else str(self.correctlyPredicted)+"\n"
        txt += "Falsely predicted:" + 'N/A' if not self.showPredictionCorrectness else str(self.falselyPredicted)+"\n"

        return txt

    def DestroyDistalSynapses(self):
        for syn in self.__node.findAllMatches("DistalSynapse"):
            syn.removeNode()
