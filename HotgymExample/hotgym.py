import csv
import datetime
import os
import numpy as np
import math

# Panda vis
from pandaBaker.pandaBaker import PandaBaker
from pandaBaker.pandaBaker import cLayer, cInput, cDataStream


from htm.bindings.sdr import SDR, Metrics
from htm.encoders.rdse import RDSE, RDSE_Parameters
from htm.encoders.date import DateEncoder
from htm.bindings.algorithms import SpatialPooler
from htm.bindings.algorithms import TemporalMemory
from htm.algorithms.anomaly_likelihood import \
    AnomalyLikelihood  # FIXME use TM.anomaly instead, but it gives worse results than the py.AnomalyLikelihood now
from htm.bindings.algorithms import Predictor

from htm.algorithms.anomaly import Anomaly

_EXAMPLE_DIR = os.path.dirname(os.path.abspath(__file__))
_INPUT_FILE_PATH = os.path.join(_EXAMPLE_DIR, "gymdata.csv")

BAKE_DATABASE_FILE_PATH = os.path.join(os.getcwd(),'bakedDatabase','hotgym.db')

default_parameters = {
    # there are 2 (3) encoders: "value" (RDSE) & "time" (DateTime weekend, timeOfDay)
    'enc': {
        "value":
            {'resolution': 0.88, 'size': 700, 'sparsity': 0.02},
        "time":
            {'timeOfDay': (30, 1), 'weekend': 21}
    },
    'predictor': {'sdrc_alpha': 0.1},
    'sp': {'boostStrength': 3.0,
           'columnCount': 1638,
           'localAreaDensity': 0.04395604395604396,
           'potentialPct': 0.85,
           'synPermActiveInc': 0.04,
           'synPermConnected': 0.13999999999999999,
           'synPermInactiveDec': 0.006},
    'tm': {'activationThreshold': 17,
           'cellsPerColumn': 13,
           'initialPerm': 0.21,
           'maxSegmentsPerCell': 128,
           'maxSynapsesPerSegment': 64,
           'minThreshold': 10,
           'newSynapseCount': 32,
           'permanenceDec': 0.1,
           'permanenceInc': 0.1},
    'anomaly': {
        'likelihood':
            {  # 'learningPeriod': int(math.floor(self.probationaryPeriod / 2.0)),
                # 'probationaryPeriod': self.probationaryPeriod-default_parameters["anomaly"]["likelihood"]["learningPeriod"],
                'probationaryPct': 0.1,
                'reestimationPeriod': 100}  # These settings are copied from NAB
    }
}

pandaBaker = PandaBaker(BAKE_DATABASE_FILE_PATH)

def main(parameters=default_parameters, argv=None, verbose=True):
    if verbose:
        import pprint
        print("Parameters:")
        pprint.pprint(parameters, indent=4)
        print("")

    # Read the input file.
    records = []
    with open(_INPUT_FILE_PATH, "r") as fin:
        reader = csv.reader(fin)
        headers = next(reader)
        next(reader)
        next(reader)
        for record in reader:
            records.append(record)

    # Make the Encoders.  These will convert input data into binary representations.
    dateEncoder = DateEncoder(timeOfDay=parameters["enc"]["time"]["timeOfDay"],
                              weekend=parameters["enc"]["time"]["weekend"])

    scalarEncoderParams = RDSE_Parameters()
    scalarEncoderParams.size = parameters["enc"]["value"]["size"]
    scalarEncoderParams.sparsity = parameters["enc"]["value"]["sparsity"]
    scalarEncoderParams.resolution = parameters["enc"]["value"]["resolution"]
    scalarEncoder = RDSE(scalarEncoderParams)
    encodingWidth = (dateEncoder.size + scalarEncoder.size)
    enc_info = Metrics([encodingWidth], 999999999)

    # Make the HTM.  SpatialPooler & TemporalMemory & associated tools.
    spParams = parameters["sp"]
    sp = SpatialPooler(
        inputDimensions=(encodingWidth,),
        columnDimensions=(spParams["columnCount"],),
        potentialPct=spParams["potentialPct"],
        potentialRadius=encodingWidth,
        globalInhibition=True,
        localAreaDensity=spParams["localAreaDensity"],
        synPermInactiveDec=spParams["synPermInactiveDec"],
        synPermActiveInc=spParams["synPermActiveInc"],
        synPermConnected=spParams["synPermConnected"],
        boostStrength=spParams["boostStrength"],
        wrapAround=True
    )
    sp_info = Metrics(sp.getColumnDimensions(), 999999999)

    tmParams = parameters["tm"]
    tm = TemporalMemory(
        columnDimensions=(spParams["columnCount"],),
        cellsPerColumn=tmParams["cellsPerColumn"],
        activationThreshold=tmParams["activationThreshold"],
        initialPermanence=tmParams["initialPerm"],
        connectedPermanence=spParams["synPermConnected"],
        minThreshold=tmParams["minThreshold"],
        maxNewSynapseCount=tmParams["newSynapseCount"],
        permanenceIncrement=tmParams["permanenceInc"],
        permanenceDecrement=tmParams["permanenceDec"],
        predictedSegmentDecrement=0.0,
        maxSegmentsPerCell=tmParams["maxSegmentsPerCell"],
        maxSynapsesPerSegment=tmParams["maxSynapsesPerSegment"]
    )
    tm_info = Metrics([tm.numberOfCells()], 999999999)

    # setup likelihood, these settings are used in NAB
    anParams = parameters["anomaly"]["likelihood"]
    probationaryPeriod = int(math.floor(float(anParams["probationaryPct"]) * len(records)))
    learningPeriod = int(math.floor(probationaryPeriod / 2.0))
    anomaly_history = AnomalyLikelihood(learningPeriod=learningPeriod,
                                        estimationSamples=probationaryPeriod - learningPeriod,
                                        reestimationPeriod=anParams["reestimationPeriod"])

    predictor = Predictor(steps=[1, 5], alpha=parameters["predictor"]['sdrc_alpha'])
    predictor_resolution = 1

    BuildPandaSystem(sp,tm, parameters["enc"]["value"]["size"],dateEncoder.size)

    # Iterate through every datum in the dataset, record the inputs & outputs.
    inputs = []
    anomaly = []
    anomalyProb = []
    predictions = {1: [], 5: []}
    iterationNo = 0

    dateBits_last = None
    consBits_last = None
    
    for count, record in enumerate(records):

        # Convert date string into Python date object.
        dateString = datetime.datetime.strptime(record[0], "%m/%d/%y %H:%M")
        # Convert data value string into float.
        consumption = float(record[1])
        inputs.append(consumption)

        # Call the encoders to create bit representations for each value.  These are SDR objects.
        dateBits = dateEncoder.encode(dateString)
        consumptionBits = scalarEncoder.encode(consumption)

        # Concatenate all these encodings into one large encoding for Spatial Pooling.
        encoding = SDR(encodingWidth).concatenate([consumptionBits, dateBits])
        enc_info.addData(encoding)

        # Create an SDR to represent active columns, This will be populated by the
        # compute method below. It must have the same dimensions as the Spatial Pooler.
        activeColumns = SDR(sp.getColumnDimensions())

        # Execute Spatial Pooling algorithm over input space.
        sp.compute(encoding, True, activeColumns)
        sp_info.addData(activeColumns)

        # Execute Temporal Memory algorithm over active mini-columns.
        # tm.compute(activeColumns, learn=True)
        tm.activateDendrites(True)
        predictiveCellsSDR = tm.getPredictiveCells()

        tm.activateCells(activeColumns, True)

        tm_info.addData(tm.getActiveCells().flatten())

        # Predict what will happen, and then train the predictor based on what just happened.
        pdf = predictor.infer(tm.getActiveCells())
        for n in (1, 5):
            if pdf[n]:
                predictions[n].append(np.argmax(pdf[n]) * predictor_resolution)
            else:
                predictions[n].append(float('nan'))

        rawAnomaly = Anomaly.calculateRawAnomaly(activeColumns,
                                                 tm.cellsToColumns(predictiveCellsSDR))

        anomalyLikelihood = anomaly_history.anomalyProbability(consumption, rawAnomaly) # need to use different calculation as we are not calling sp.compute(..)
        anomaly.append(rawAnomaly)
        anomalyProb.append(anomalyLikelihood)

        predictor.learn(count, tm.getActiveCells(), int(consumption / predictor_resolution))

        # ------------------HTMpandaVis----------------------
        # fill up values

        pandaBaker.inputs["Consumption"].stringValue = "consumption: {:.2f}".format(consumption)
        pandaBaker.inputs["Consumption"].bits = consumptionBits.sparse

        pandaBaker.inputs["TimeOfDay"].stringValue = record[0]
        pandaBaker.inputs["TimeOfDay"].bits = dateBits.sparse

        pandaBaker.layers["Layer1"].activeColumns = activeColumns.sparse
        pandaBaker.layers["Layer1"].winnerCells = tm.getWinnerCells().sparse
        pandaBaker.layers["Layer1"].predictiveCells = predictiveCellsSDR.sparse
        pandaBaker.layers["Layer1"].activeCells = tm.getActiveCells().sparse

        # customizable datastreams to be show on the DASH PLOTS
        pandaBaker.dataStreams["rawAnomaly"].value = rawAnomaly
        pandaBaker.dataStreams["powerConsumption"].value = consumption
        pandaBaker.dataStreams["numberOfWinnerCells"].value = len(tm.getWinnerCells().sparse)
        pandaBaker.dataStreams["numberOfPredictiveCells"].value = len(predictiveCellsSDR.sparse)
        pandaBaker.dataStreams["consumptionInput_sparsity"].value = consumptionBits.getSparsity()
        pandaBaker.dataStreams["dateInput_sparsity"].value = dateBits.getSparsity()
        pandaBaker.dataStreams["consumptionInput_overlap_with_prev_step"].value = 0 if consBits_last is None else consumptionBits.getOverlap(consBits_last)
        consBits_last = consumptionBits
        pandaBaker.dataStreams["dateInput_overlap_with_prev_step"].value = 0 if dateBits_last is None else dateBits.getOverlap(dateBits_last)
        dateBits_last = dateBits

        pandaBaker.dataStreams["Layer1_SP_overlap_metric"].value = sp_info.overlap.overlap
        pandaBaker.dataStreams["Layer1_TM_overlap_metric"].value = sp_info.overlap.overlap
        pandaBaker.dataStreams["Layer1_SP_activation_frequency"].value = sp_info.activationFrequency.mean()
        pandaBaker.dataStreams["Layer1_TM_activation_frequency"].value = tm_info.activationFrequency.mean()
        pandaBaker.dataStreams["Layer1_SP_entropy"].value = sp_info.activationFrequency.mean()
        pandaBaker.dataStreams["Layer1_TM_entropy"].value = tm_info.activationFrequency.mean()

        
        pandaBaker.StoreIteration(iterationNo)

        print("ITERATION: "+str(iterationNo))

        # ------------------HTMpandaVis----------------------



        iterationNo = iterationNo + 1

        #pandaBaker.CommitBatch()
        if iterationNo == 1000:
            break

    pandaBaker.CommitBatch()

    # Print information & statistics about the state of the HTM.
    print("Encoded Input", enc_info)
    print("")
    print("Spatial Pooler Mini-Columns", sp_info)
    print(str(sp))
    print("")
    print("Temporal Memory Cells", tm_info)
    print(str(tm))
    print("")

    # Shift the predictions so that they are aligned with the input they predict.
    for n_steps, pred_list in predictions.items():
        for x in range(n_steps):
            pred_list.insert(0, float('nan'))
            pred_list.pop()

    # Calculate the predictive accuracy, Root-Mean-Squared
    accuracy = {1: 0, 5: 0}
    accuracy_samples = {1: 0, 5: 0}

    for idx, inp in enumerate(inputs):
        for n in predictions:  # For each [N]umber of time steps ahead which was predicted.
            val = predictions[n][idx]
            if not math.isnan(val):
                accuracy[n] += (inp - val) ** 2
                accuracy_samples[n] += 1
    for n in sorted(predictions):
        if accuracy_samples[n]!=0:
            accuracy[n] = (accuracy[n] / accuracy_samples[n]) ** .5
            print("Predictive Error (RMS)", n, "steps ahead:", accuracy[n])
        else:
            print("Unable to calculate RMS error!")

    # Show info about the anomaly (mean & std)
    print("Anomaly Mean", np.mean(anomaly))
    print("Anomaly Std ", np.std(anomaly))

    # Plot the Predictions and Anomalies.
    if verbose:
        try:
            import matplotlib.pyplot as plt
        except:
            print("WARNING: failed to import matplotlib, plots cannot be shown.")
            return -accuracy[5]

        plt.subplot(2, 1, 1)
        plt.title("Predictions")
        plt.xlabel("Time")
        plt.ylabel("Power Consumption")
        plt.plot(np.arange(len(inputs)), inputs, 'red',
                 np.arange(len(inputs)), predictions[1], 'blue',
                 np.arange(len(inputs)), predictions[5], 'green', )
        plt.legend(labels=('Input', '1 Step Prediction, Shifted 1 step', '5 Step Prediction, Shifted 5 steps'))

        plt.subplot(2, 1, 2)
        plt.title("Anomaly Score")
        plt.xlabel("Time")
        plt.ylabel("Power Consumption")
        inputs = np.array(inputs) / max(inputs)
        plt.plot(np.arange(len(inputs)), inputs, 'red',
                 np.arange(len(inputs)), anomaly, 'blue', )
        plt.legend(labels=('Input', 'Anomaly Score'))
        plt.show()

    return -accuracy[5]


#with this method, the structure for visualization is defined
def BuildPandaSystem(sp,tm,consumptionBits_size,dateBits_size):

    #we have two inputs connected to proximal synapses of Layer1
    pandaBaker.inputs["Consumption"] = cInput(consumptionBits_size)
    pandaBaker.inputs["TimeOfDay"] = cInput(dateBits_size)

    pandaBaker.layers["Layer1"] = cLayer(sp,tm) # Layer1 has Spatial Pooler & Temporal Memory
    pandaBaker.layers["Layer1"].proximalInputs = [
        "Consumption",
        "TimeOfDay",
    ]

    #data for dash plots
    streams = ["rawAnomaly","powerConsumption","numberOfWinnerCells","numberOfPredictiveCells",
               "consumptionInput_sparsity","dateInput_sparsity","consumptionInput_overlap_with_prev_step",
               "dateInput_overlap_with_prev_step","Layer1_SP_overlap_metric","Layer1_TM_overlap_metric",
               "Layer1_SP_activation_frequency","Layer1_TM_activation_frequency","Layer1_SP_entropy",
               "Layer1_TM_entropy"
               ]

    pandaBaker.dataStreams = dict((name,cDataStream()) for name in streams)# create dicts for more comfortable code
    #could be also written like: pandaBaker.dataStreams["myStreamName"] = cDataStream()

    pandaBaker.PrepareDatabase()

if __name__ == "__main__":
    try:
        #while True:  # run infinitely
        main()

    except KeyboardInterrupt:
        print("Keyboard interrupt")
    print("Script finished")
