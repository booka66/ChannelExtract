import math
from multiprocessing import Pool
import sys
from alert import alert

import pywt
import tempfile

# print(sys.version_info)
# assert (sys.version_info[0], sys.version_info[1]) == (
#     3,
#     7,
# ), "Please install/setup Python environment: Version-3.7"

import numpy as np
import h5py
import json
import os
import time
import scipy
import scipy.signal

from tqdm import tqdm
import clr  # pip install pythonnet

# For the code to run, BrianWave5 software needs to be installed, the path for the *.dll files should be changed below accordingly
clr.AddReference(
    os.path.join("C:\\Program Files\\3Brain\\BrainWave 5", "3Brain.BrainWave.IO.dll")
)

from System import Int32, Double, Boolean
from _3Brain.BrainWave.IO import BrwFile
from _3Brain.BrainWave.Common import (
    MeaFileExperimentInfo,
    RawDataSettings,
    ExperimentType,
    MeaPlate,
)
from _3Brain.Common import MeaPlateModel, MeaChipRoi, MeaDataType, ChCoord


def getChMap():
    newChs = np.zeros(4096, dtype=[("Row", "<i2"), ("Col", "<i2")])
    idx = 0
    for idx in range(4096):
        column = (idx // 64) + 1
        row = idx % 64 + 1
        if row == 0:
            row = 64
        if column == 0:
            column = 1

        newChs[idx] = (np.int16(row), np.int16(column))
        ind = np.lexsort((newChs["Col"], newChs["Row"]))
    return newChs[ind]


class writeBrw:
    def __init__(self, inputFilePath, outputFile, parameters):
        self.path = inputFilePath
        self.fileName = outputFile
        # self.brw = h5py.File(self.path, 'r')
        self.description = parameters["Ver"]
        self.version = parameters["Typ"]
        self.samplingrate = parameters["samplingRate"]
        self.frames = parameters["nRecFrames"]
        self.signalInversion = parameters["signalInversion"]
        self.maxVolt = parameters["maxUVolt"]
        self.minVolt = parameters["minUVolt"]
        self.bitdepth = parameters["bitDepth"]
        self.chs = parameters["recElectrodeList"]
        self.QLevel = np.power(2, parameters["bitDepth"])
        self.fromQLevelToUVolt = (self.maxVolt - self.minVolt) / self.QLevel

        # self.signalInversion = self.brw['3BRecInfo/3BRecVars/SignalInversion']
        # self.maxVolt = self.brw['3BRecInfo/3BRecVars/MaxVolt'][0]
        # self.minVolt = self.brw['3BRecInfo/3BRecVars/MinVolt'][0]
        # self.QLevel = np.power(2, self.brw['3BRecInfo/3BRecVars/BitDepth'][0])
        # self.fromQLevelToUVolt = (self.maxVolt - self.minVolt) / self.QLevel

    def createNewBrw(self):
        newName = self.fileName
        new = h5py.File(newName, "w")

        new.attrs.__setitem__("Description", self.description)
        # new.attrs.__setitem__('GUID', self.brw.attrs['GUID'])
        new.attrs.__setitem__("Version", self.version)

        # new.copy(self.brw['3BRecInfo'], dest=new)
        # new.copy(self.brw['3BUserInfo'], dest=new)
        new.create_dataset("/3BRecInfo/3BRecVars/SamplingRate", data=[np.float64(100)])
        # new.create_dataset('/3BRecInfo/3BRecVars/NewSampling', data=[np.float64(self.samplingrate)])
        new.create_dataset(
            "/3BRecInfo/3BRecVars/NRecFrames", data=[np.float64(self.frames)]
        )
        new.create_dataset(
            "/3BRecInfo/3BRecVars/SignalInversion",
            data=[np.int32(self.signalInversion)],
        )
        new.create_dataset(
            "/3BRecInfo/3BRecVars/MaxVolt", data=[np.int32(self.maxVolt)]
        )
        new.create_dataset(
            "/3BRecInfo/3BRecVars/MinVolt", data=[np.int32(self.minVolt)]
        )
        new.create_dataset(
            "/3BRecInfo/3BRecVars/BitDepth", data=[np.int32(self.bitdepth)]
        )
        new.create_dataset("/3BRecInfo/3BMeaStreams/Raw/Chs", data=[self.chs])

        # new.attrs.__setitem__('Description', self.brw.attrs['Description'])
        # new.attrs.__setitem__('GUID', self.brw.attrs['GUID'])
        # new.attrs.__setitem__('Version', self.brw.attrs['Version'])

        # new.copy(self.brw['3BRecInfo'], dest=new)
        # new.copy(self.brw['3BUserInfo'], dest=new)

        try:
            del new["/3BRecInfo/3BMeaStreams/Raw/Chs"]
        except:
            del new["/3BRecInfo/3BMeaStreams/WaveletCoefficients/Chs"]

        del new["/3BRecInfo/3BRecVars/NRecFrames"]
        del new["/3BRecInfo/3BRecVars/SamplingRate"]

        self.newDataset = new
        # self.brw.close()

    def writeRaw(self, rawToWrite, typeFlatten="F"):
        # rawToWrite = rawToWrite / self.fromQLevelToUVolt
        # rawToWrite = (rawToWrite + (self.QLevel / 2)) * self.signalInversion

        if rawToWrite.ndim == 1:
            newRaw = rawToWrite
        else:
            newRaw = np.int16(rawToWrite.flatten(typeFlatten))

        if "/3BData/Raw" in self.newDataset:
            dset = self.newDataset["3BData/Raw"]
            dset.resize((dset.shape[0] + newRaw.shape[0],))
            dset[-newRaw.shape[0] :] = newRaw

        else:
            self.newDataset.create_dataset("/3BData/Raw", data=newRaw, maxshape=(None,))

    def writeChs(self, chs):
        self.newDataset.create_dataset("/3BRecInfo/3BMeaStreams/Raw/Chs", data=chs)

    def witeFrames(self, frames):
        self.newDataset.create_dataset(
            "/3BRecInfo/3BRecVars/NRecFrames", data=[np.int64(frames)]
        )

    def writeSamplingFreq(self, fs):
        self.newDataset.create_dataset(
            "/3BRecInfo/3BRecVars/SamplingRate", data=[np.float64(fs)]
        )

    def appendBrw(self, fName, frames, rawToAppend, typeFlatten="F"):
        brwAppend = h5py.File(fName, "a")

        signalInversion = brwAppend["3BRecInfo/3BRecVars/SignalInversion"]
        maxVolt = brwAppend["3BRecInfo/3BRecVars/MaxVolt"][0]
        minVolt = brwAppend["3BRecInfo/3BRecVars/MinVolt"][0]
        QLevel = np.power(2, brwAppend["3BRecInfo/3BRecVars/BitDepth"][0])
        fromQLevelToUVolt = (maxVolt - minVolt) / QLevel

        newFrame = frames
        del brwAppend["/3BRecInfo/3BRecVars/NRecFrames"]
        brwAppend.create_dataset(
            "/3BRecInfo/3BRecVars/NRecFrames", data=[np.int64(newFrame)]
        )

        if rawToAppend.ndim != 1:
            rawToAppend = np.int16(rawToAppend.flatten(typeFlatten))

        dset = brwAppend["3BData/Raw"]
        dset.resize((dset.shape[0] + rawToAppend.shape[0],))
        dset[-rawToAppend.shape[0] :] = rawToAppend

        brwAppend.close()

    def close(self):
        self.newDataset.close()
        # self.brw.close()


def parameter(h5):
    parameters = {}
    parameters["nRecFrames"] = h5["/3BRecInfo/3BRecVars/NRecFrames"][0]
    parameters["samplingRate"] = h5["/3BRecInfo/3BRecVars/SamplingRate"][0]
    parameters["recordingLength"] = (
        parameters["nRecFrames"] / parameters["samplingRate"]
    )
    parameters["signalInversion"] = h5["/3BRecInfo/3BRecVars/SignalInversion"][
        0
    ]  # depending on the acq version it can be 1 or -1
    parameters["maxUVolt"] = h5["/3BRecInfo/3BRecVars/MaxVolt"][0]  # in uVolt
    parameters["minUVolt"] = h5["/3BRecInfo/3BRecVars/MinVolt"][0]  # in uVolt
    parameters["bitDepth"] = h5["/3BRecInfo/3BRecVars/BitDepth"][
        0
    ]  # number of used bit of the 2 byte coding
    parameters["qLevel"] = (
        2 ^ parameters["bitDepth"]
    )  # quantized levels corresponds to 2^num of bit to encode the signal
    parameters["fromQLevelToUVolt"] = (
        parameters["maxUVolt"] - parameters["minUVolt"]
    ) / parameters["qLevel"]
    parameters["recElectrodeList"] = list(
        h5["/3BRecInfo/3BMeaStreams/Raw/Chs"]
    )  # list of the recorded channels
    parameters["numRecElectrodes"] = len(parameters["recElectrodeList"])
    return parameters


def Digital_to_Analog(parameters):
    ADCCountsToMV = parameters["signalInversion"] * parameters["fromQLevelToUVolt"]
    MVOffset = parameters["signalInversion"] * parameters["minUVolt"]
    return ADCCountsToMV, MVOffset


def downsample_channel(data, freq_ratio):
    # s = time.time()
    re_sampleRatio = int(data.shape[0] / freq_ratio)
    data_downsampled = scipy.signal.resample(data, re_sampleRatio)
    return data_downsampled


def get_chfile_properties(path):
    fileInfo = {}
    h5 = h5py.File(path, "r")
    fileInfo["recFrames"] = h5["/3BRecInfo/3BRecVars/NRecFrames"][0]
    fileInfo["recSampling"] = h5["/3BRecInfo/3BRecVars/SamplingRate"][0]
    fileInfo["newSampling"] = h5["/3BRecInfo/3BRecVars/NewSampling"][0]
    # fileInfo['newSampling'] = 1024
    fileInfo["recLength"] = fileInfo["recFrames"] / fileInfo["recSampling"]
    fileInfo["recElectrodeList"] = h5["/3BRecInfo/3BMeaStreams/Raw/Chs"][
        :
    ]  # list of the recorded channels
    fileInfo["numRecElectrodes"] = len(fileInfo["recElectrodeList"])
    fileInfo["Ver"] = h5["/3BRecInfo/3BRecVars/Ver"][0]
    fileInfo["Typ"] = h5["/3BRecInfo/3BRecVars/Typ"][0]
    fileInfo["start"] = h5["/3BRecInfo/3BRecVars/startTime"][0]
    fileInfo["end"] = h5["/3BRecInfo/3BRecVars/endTime"][0]

    h5.close()
    return fileInfo


def get_recFile_properties(path, typ):
    h5 = h5py.File(path, "r")
    print(typ.decode("utf8"))
    if typ.decode("utf8").lower() == "bw4":
        parameters = {}
        parameters["Ver"] = "BW4"

        parameters["nRecFrames"] = h5["/3BRecInfo/3BRecVars/NRecFrames"][0]
        parameters["samplingRate"] = h5["/3BRecInfo/3BRecVars/SamplingRate"][0]
        parameters["recordingLength"] = (
            parameters["nRecFrames"] / parameters["samplingRate"]
        )
        parameters["signalInversion"] = h5["/3BRecInfo/3BRecVars/SignalInversion"][
            0
        ]  # depending on the acq version it can be 1 or -1
        parameters["maxUVolt"] = h5["/3BRecInfo/3BRecVars/MaxVolt"][0]  # in uVolt
        parameters["minUVolt"] = h5["/3BRecInfo/3BRecVars/MinVolt"][0]  # in uVolt
        parameters["bitDepth"] = h5["/3BRecInfo/3BRecVars/BitDepth"][
            0
        ]  # number of used bit of the 2 byte coding
        parameters["qLevel"] = (
            2 ^ parameters["bitDepth"]
        )  # quantized levels corresponds to 2^num of bit to encode the signal
        parameters["fromQLevelToUVolt"] = (
            parameters["maxUVolt"] - parameters["minUVolt"]
        ) / parameters["qLevel"]
        try:
            parameters["recElectrodeList"] = h5["/3BRecInfo/3BMeaStreams/Raw/Chs"][
                :
            ]  # list of the recorded channels
            parameters["Typ"] = "RAW"
        except:
            parameters["recElectrodeList"] = h5[
                "/3BRecInfo/3BMeaStreams/WaveletCoefficients/Chs"
            ][:]
            parameters["Typ"] = "WAV"
        parameters["numRecElectrodes"] = len(parameters["recElectrodeList"])

    else:
        if "Raw" in h5["Well_A1"].keys():
            json_s = json.loads(h5["ExperimentSettings"][0].decode("utf8"))
            parameters = {}
            parameters["Ver"] = "BW5"
            parameters["Typ"] = "RAW"
            parameters["nRecFrames"] = h5["Well_A1/Raw"].shape[0] // 4096
            parameters["samplingRate"] = json_s["TimeConverter"]["FrameRate"]
            parameters["recordingLength"] = (
                parameters["nRecFrames"] / parameters["samplingRate"]
            )
            parameters["signalInversion"] = int(
                1
            )  # depending on the acq version it can be 1 or -1
            parameters["maxUVolt"] = int(4125)  # in uVolt
            parameters["minUVolt"] = int(-4125)  # in uVolt
            parameters["bitDepth"] = int(12)  # number of used bit of the 2 byte coding
            parameters["qLevel"] = (
                2 ^ parameters["bitDepth"]
            )  # quantized levels corresponds to 2^num of bit to encode the signal
            parameters["fromQLevelToUVolt"] = (
                parameters["maxUVolt"] - parameters["minUVolt"]
            ) / parameters["qLevel"]
            parameters["recElectrodeList"] = getChMap()[
                :
            ]  # list of the recorded channels
            parameters["numRecElectrodes"] = len(parameters["recElectrodeList"])
        else:
            json_s = json.loads(h5["ExperimentSettings"][0].decode("utf8"))
            parameters = {}
            parameters["Ver"] = "BW5"
            parameters["Typ"] = "WAV"
            samplingRate = h5.attrs["SamplingRate"]
            nChannels = len(h5["Well_A1/StoredChIdxs"])
            coefsTotalLength = len(h5["Well_A1/WaveletBasedEncodedRaw"])
            compressionLevel = h5["Well_A1/WaveletBasedEncodedRaw"].attrs[
                "CompressionLevel"
            ]
            framesChunkLength = h5["Well_A1/WaveletBasedEncodedRaw"].attrs[
                "DataChunkLength"
            ]
            coefsChunkLength = (
                math.ceil(framesChunkLength / pow(2, compressionLevel)) * 2
            )
            numFrames = 0
            chIdx = 1
            coefsPosition = chIdx * coefsChunkLength
            while coefsPosition < coefsTotalLength:
                length = int(coefsChunkLength / 2)
                for i in range(compressionLevel):
                    length *= 2
                numFrames += length
                coefsPosition += coefsChunkLength * nChannels

            parameters["nRecFrames"] = numFrames
            parameters["recordingLength"] = numFrames / samplingRate
            parameters["samplingRate"] = json_s["TimeConverter"]["FrameRate"]
            parameters["signalInversion"] = int(
                1
            )  # depending on the acq version it can be 1 or -1
            parameters["maxUVolt"] = int(4125)  # in uVolt
            parameters["minUVolt"] = int(-4125)  # in uVolt
            parameters["bitDepth"] = int(12)  # number of used bit of the 2 byte coding
            parameters["qLevel"] = (
                2 ^ parameters["bitDepth"]
            )  # quantized levels corresponds to 2^num of bit to encode the signal
            parameters["fromQLevelToUVolt"] = (
                parameters["maxUVolt"] - parameters["minUVolt"]
            ) / parameters["qLevel"]
            parameters["recElectrodeList"] = getChMap()[
                :
            ]  # list of the recorded channels
            parameters["numRecElectrodes"] = len(parameters["recElectrodeList"])

    return parameters


def extBW4_WAV(chfileName, recfileName, chfileInfo, parameters):
    with h5py.File(chfileName) as file:
        start_time = file["3BRecInfo/3BRecVars/startTime"][0]
        end_time = file["3BRecInfo/3BRecVars/endTime"][0]
        print(f"Start time: {start_time}")
        print(f"End time: {end_time}")
        file.close()

    start_frame = int(start_time * parameters["samplingRate"])
    end_frame = int(end_time * parameters["samplingRate"])
    print(f"Start frame: {start_frame}")
    print(f"End frame: {end_frame}")

    b = time.time()
    chs, ind_rec, ind_ch = np.intersect1d(
        parameters["recElectrodeList"],
        chfileInfo["recElectrodeList"],
        return_indices=True,
    )
    newSampling = int(chfileInfo["newSampling"])
    output_file_name = recfileName.split(".")[0] + "_resample_" + str(newSampling)
    output_path = output_file_name + ".brw"
    # print(output_path)
    parameters["freq_ratio"] = parameters["samplingRate"] / chfileInfo["newSampling"]
    fs = chfileInfo["newSampling"]  # desired sampling frequency
    block_size = 1000000

    print("Downsampling File # ", output_path)
    dset = writeBrw(recfileName, output_path, parameters)
    dset.createNewBrw()

    newChs = np.zeros(len(chs), dtype=[("Row", "<i2"), ("Col", "<i2")])
    idx = 0
    for ch in chs:
        newChs[idx] = (np.int16(ch[0]), np.int16(ch[1]))
        idx += 1

    ind = np.lexsort((newChs["Col"], newChs["Row"]))
    newChs = newChs[ind]
    consumer = object()
    data = BrwFile.Open(recfileName)
    info = data.get_MeaExperimentInfo()
    dur = int(info.get_TimeDuration().get_TotalSeconds())
    numReading = int(np.floor(dur * info.get_SamplingRate() / block_size))

    s = time.time()
    nrecFrame = 0
    for cnk in tqdm(range(numReading), desc="Export & downsampling Progress"):
        if start_frame + cnk * block_size >= end_frame:
            break
        raw = np.zeros((block_size, len(ind_rec)))

        tmp = data.ReadRawData(
            int(start_frame + cnk * block_size),
            block_size,
            data.get_SourceChannels(),
            consumer,
        )
        # tmp is a 3D array, first index is the well number (in case of mutliwells, for single chip there will be only one well),
        # the second index is the channel, the third index the time frame
        count = 0
        for i in tqdm(ind_rec, desc="Extracting individual channel"):
            ext = np.fromiter(
                tmp[0][int(i)], int
            )  # here values are converted in voltage
            raw[:, count] = ext[:]
            count += 1

        raw_resample = downsample_channel(raw, parameters["freq_ratio"])
        raw_resample = np.transpose(raw_resample)

        nrecFrame += raw_resample.shape[1]

        if cnk <= 0:
            dset.writeRaw(raw_resample[ind, :], typeFlatten="F")
            dset.writeSamplingFreq(fs)
            dset.witeFrames(nrecFrame)
            dset.writeChs(newChs)
            dset.close()
        else:
            dset.appendBrw(output_path, nrecFrame, raw_resample[ind, :])
    data.Close()
    return time.time() - s, output_path


def extBW4_RAW(chfileName, recfileName, chfileInfo, parameters):
    chs, ind_rec, ind_ch = np.intersect1d(
        parameters["recElectrodeList"],
        chfileInfo["recElectrodeList"],
        return_indices=True,
    )
    newSampling = int(chfileInfo["newSampling"])
    output_file_name = recfileName.split(".")[0] + "_resample_" + str(newSampling)
    output_path = output_file_name + ".brw"
    # print(parameters)
    parameters["freq_ratio"] = parameters["samplingRate"] / chfileInfo["newSampling"]
    fs = chfileInfo["newSampling"]  # desired sampling frequency
    block_size = 100000

    chunks = np.arange(block_size, parameters["nRecFrames"], block_size)
    print("Downsampling File #", output_path)
    dset = writeBrw(recfileName, output_path, parameters)
    dset.createNewBrw()

    newChs = np.zeros(len(chs), dtype=[("Row", "<i2"), ("Col", "<i2")])
    idx = 0
    for ch in chs:
        newChs[idx] = (np.int16(ch[0]), np.int16(ch[1]))
        idx += 1

    ind = np.lexsort((newChs["Col"], newChs["Row"]))
    newChs = newChs[ind]

    start = 0
    h5 = h5py.File(recfileName, "r")
    idx_a = ind_rec.copy()
    idd = []
    for i in range(block_size):
        idd.extend(idx_a)
        idx_a = idx_a + parameters["numRecElectrodes"]

    s = time.time()
    nrecFrame = 0
    for cnk in tqdm(chunks, desc="Downsampling & Export Progress"):
        end = cnk * parameters["numRecElectrodes"]
        data = np.array(h5["/3BData/Raw"][start:end])
        data = data[idd]
        data = data.reshape(block_size, len(chs))

        data_resample = downsample_channel(data, parameters["freq_ratio"])
        resamp_frame = data_resample.shape[0]

        nrecFrame += resamp_frame
        res = np.zeros((len(chs), resamp_frame))

        ch = 0
        for channel in range(res.shape[0]):
            res[channel, :] = data_resample[:, ch]
            ch += 1

        if cnk <= block_size:
            dset.writeRaw(res[ind, :], typeFlatten="F")
            dset.writeSamplingFreq(fs)
            dset.witeFrames(nrecFrame)
            dset.writeChs(newChs)
            dset.close()
        else:
            dset.appendBrw(output_path, nrecFrame, res[ind, :])

        start = end
    h5.close()
    totTime = time.time() - s

    return totTime, output_path


def reconstruct_WAV_signal(
    recfileName,
    channel_index,
    samplingRate,
    nChannels,
    coefsTotalLength,
    compressionLevel,
    framesChunkLength,
    coefsChunkLength,
):
    data = []
    with h5py.File(recfileName) as file:
        coefs_position = channel_index * coefsChunkLength
        while coefs_position < coefsTotalLength:
            coefs = file["Well_A1/WaveletBasedEncodedRaw"][
                coefs_position : coefs_position + coefsChunkLength
            ]
            length = int(len(coefs) / 2)

            approx, details = coefs[:length], coefs[length:]
            approx = np.roll(approx, -5)
            details = np.roll(details, -5)

            length = int(len(coefs) / 2)
            frames = pywt.idwt(approx, details, "sym7", "periodization")
            length *= 2
            for i in range(1, compressionLevel):
                frames = pywt.idwt(frames[:length], None, "sym7", "periodization")
                length *= 2
            data.extend(frames[2:-2])
            coefs_position += coefsChunkLength * nChannels
    return data


def extract_channel(args):
    (
        i,
        recfileName,
        samplingRate,
        nChannels,
        coefsTotalLength,
        compressionLevel,
        framesChunkLength,
        coefsChunkLength,
        chfileInfo,
    ) = args
    channel_data = reconstruct_WAV_signal(
        recfileName,
        i,
        samplingRate,
        nChannels,
        coefsTotalLength,
        compressionLevel,
        framesChunkLength,
        coefsChunkLength,
    )
    original_sampling_rate = samplingRate
    desired_sampling_rate = chfileInfo["newSampling"]
    downsample_factor = math.floor(original_sampling_rate / desired_sampling_rate)
    new_sampling_rate = original_sampling_rate / downsample_factor
    downsampled_channel_data = channel_data[::downsample_factor]
    return downsampled_channel_data


def extBW5_WAV(chfileName, recfileName, chfileInfo, parameters):
    # open the BRW file
    samplingRate = None
    nChannels = None
    coefsTotalLength = None
    compressionLevel = None
    framesChunkLength = None
    coefsChunkLength = None
    with h5py.File(chfileName) as file:
        start_time = file["3BRecInfo/3BRecVars/startTime"][0]
        end_time = file["3BRecInfo/3BRecVars/endTime"][0]
        print(f"Start time: {start_time}")
        print(f"End time: {end_time}")
        file.close()

    with h5py.File(recfileName) as file:
        # collect experiment information
        samplingRate = file.attrs["SamplingRate"]
        nChannels = len(file["Well_A1/StoredChIdxs"])
        coefsTotalLength = len(file["Well_A1/WaveletBasedEncodedRaw"])
        compressionLevel = file["Well_A1/WaveletBasedEncodedRaw"].attrs[
            "CompressionLevel"
        ]
        framesChunkLength = file["Well_A1/WaveletBasedEncodedRaw"].attrs[
            "DataChunkLength"
        ]
        coefsChunkLength = math.ceil(framesChunkLength / pow(2, compressionLevel)) * 2
        file.close()

    chs, ind_rec, ind_ch = np.intersect1d(
        parameters["recElectrodeList"],
        chfileInfo["recElectrodeList"],
        return_indices=True,
    )
    newSampling = int(chfileInfo["newSampling"])
    output_file_name = recfileName.split(".")[0] + "_resample_" + str(newSampling)
    output_path = output_file_name + ".brw"
    parameters["freq_ratio"] = parameters["samplingRate"] / chfileInfo["newSampling"]
    fs = chfileInfo["newSampling"]  # desired sampling frequency

    print("Downsampling File # ", output_path)
    dset = writeBrw(recfileName, output_path, parameters)
    dset.createNewBrw()

    newChs = np.zeros(len(chs), dtype=[("Row", "<i2"), ("Col", "<i2")])
    idx = 0
    for ch in chs:
        newChs[idx] = (np.int16(ch[0]), np.int16(ch[1]))
        idx += 1

    ind = np.lexsort((newChs["Col"], newChs["Row"]))
    newChs = newChs[ind]
    idx_a = ind_rec.copy()
    print(idx_a)
    data = BrwFile.Open(recfileName)

    s = time.time()

    args = [
        (
            i,
            recfileName,
            samplingRate,
            nChannels,
            coefsTotalLength,
            compressionLevel,
            framesChunkLength,
            coefsChunkLength,
            chfileInfo,
        )
        for i in idx_a
    ]

    with Pool() as pool:
        results = list(
            tqdm(
                pool.map(extract_channel, args),
                total=len(args),
                desc="Extracting channels",
            )
        )

    original_sampling_rate = parameters["samplingRate"]
    desired_sampling_rate = chfileInfo["newSampling"]
    downsample_factor = math.floor(original_sampling_rate / desired_sampling_rate)
    new_sampling_rate = original_sampling_rate / downsample_factor
    print(f"Mine: {new_sampling_rate}")
    print(f"Original: {fs}")

    chunk_size = 100000  # Adjust the chunk size as needed
    nrecFrame = len(results[0])

    for i in range(0, nrecFrame, chunk_size):
        start = i
        end = min(i + chunk_size, nrecFrame)

        raw_chunk = [results[j][start:end] for j in range(len(results))]
        raw_chunk = np.array(raw_chunk)

        if i == 0:
            dset.writeRaw(raw_chunk, typeFlatten="F")
            dset.writeSamplingFreq(new_sampling_rate)
            dset.witeFrames(nrecFrame)
            dset.writeChs(newChs)
        else:
            dset.appendBrw(output_path, end, raw_chunk)

    dset.close()
    data.Close()

    return time.time() - s, output_path


def extBW5_RAW(chfileName, recfileName, chfileInfo, parameters):
    chs, ind_rec, ind_ch = np.intersect1d(
        parameters["recElectrodeList"],
        chfileInfo["recElectrodeList"],
        return_indices=True,
    )
    newSampling = int(chfileInfo["newSampling"])
    output_file_name = recfileName.split(".")[0] + "_resample_" + str(newSampling)
    output_path = output_file_name + ".brw"
    parameters["freq_ratio"] = parameters["samplingRate"] / chfileInfo["newSampling"]
    fs = chfileInfo["newSampling"]  # desired sampling frequency
    block_size = 100000

    chunks = np.arange(block_size, parameters["nRecFrames"], block_size)
    print("Downsampling File #", output_path)
    dset = writeBrw(recfileName, output_path, parameters)
    dset.createNewBrw()

    newChs = np.zeros(len(chs), dtype=[("Row", "<i2"), ("Col", "<i2")])
    idx = 0
    for ch in chs:
        newChs[idx] = (np.int16(ch[0]), np.int16(ch[1]))
        idx += 1

    ind = np.lexsort((newChs["Col"], newChs["Row"]))
    newChs = newChs[ind]

    start = 0
    h5 = h5py.File(recfileName, "r")
    idx_a = ind_rec.copy()
    idd = []
    for i in range(block_size):
        idd.extend(idx_a)
        idx_a = idx_a + parameters["numRecElectrodes"]

    s = time.time()
    nrecFrame = 0

    for cnk in tqdm(chunks, desc="Downsampling & Export Progress"):
        end = int(cnk * float(parameters["numRecElectrodes"]))
        data = np.array(h5["Well_A1/Raw"][start:end])
        data = data[idd]
        data = data.reshape(block_size, len(chs))

        data_resample = downsample_channel(data, parameters["freq_ratio"])
        resamp_frame = data_resample.shape[0]

        nrecFrame += resamp_frame
        res = np.zeros((len(chs), resamp_frame))

        ch = 0
        for channel in range(res.shape[0]):
            res[channel, :] = data_resample[:, ch]
            ch += 1

        if cnk <= block_size:
            dset.writeRaw(res[ind, :], typeFlatten="F")
            dset.writeSamplingFreq(fs)
            dset.witeFrames(nrecFrame)
            dset.writeChs(newChs)
            dset.close()
        else:
            dset.appendBrw(output_path, nrecFrame, res[ind, :])

        start = end

    h5.close()

    totTime = time.time() - s

    return totTime, output_path


def file_check(path, filename):
    #    chfileName = path+"\\"+filename
    chfilePath = os.path.join(path, filename)
    chfileInfo = get_chfile_properties(chfilePath)

    recfileName = "_".join(filename.split("_")[0:-1]) + ".brw"
    recfilePath = os.path.join(path, recfileName)

    parameters = get_recFile_properties(recfilePath, chfileInfo["Ver"].lower())

    if (
        parameters["nRecFrames"] == chfileInfo["recFrames"]
        and parameters["samplingRate"] == chfileInfo["recSampling"]
    ):
        filematch = True
    else:
        filematch = False

    return (chfilePath, recfilePath, chfileInfo, parameters, filematch)


def run(drive_letter, folder):
    fileCount = 1
    os.chdir(drive_letter)
    for filename in os.listdir(folder):
        filematch = False
        if filename.split("_")[-1] == "exportCh.brw":
            chfileName, recfileName, chfileInfo, parameters, filematch = file_check(
                folder, filename
            )

        if (
            filematch
            and chfileInfo["Ver"].decode("utf8") == "BW4"
            and chfileInfo["Typ"].decode("utf8") == "WAV"
        ):
            totTime, output_path = extBW4_WAV(
                chfileName, recfileName, chfileInfo, parameters
            )
            print(
                "\n #",
                fileCount,
                " Down Sampled Output File Location: ",
                output_path,
                "\n Time to Downsample: ",
                totTime,
            )

        elif (
            filematch
            and chfileInfo["Ver"].decode("utf8") == "BW4"
            and chfileInfo["Typ"].decode("utf8") == "RAW"
        ):
            totTime, output_path = extBW4_RAW(
                chfileName, recfileName, chfileInfo, parameters
            )
            print(
                "\n #",
                fileCount,
                " Down Sampled Output File Location: ",
                output_path,
                "\n Time to Downsample: ",
                totTime,
            )

        elif (
            filematch
            and chfileInfo["Ver"].decode("utf8") == "BW5"
            and chfileInfo["Typ"].decode("utf8") == "RAW"
        ):
            totTime, output_path = extBW5_WAV(
                chfileName, recfileName, chfileInfo, parameters
            )
            print(
                "\n #",
                fileCount,
                " Down Sampled Output File Location: ",
                output_path,
                "\n Time to Downsample: ",
                totTime,
            )

        elif (
            filematch
            and chfileInfo["Ver"].decode("utf8") == "BW5"
            and chfileInfo["Typ"].decode("utf8") == "WAV"
        ):
            totTime, output_path = extBW5_WAV(
                chfileName, recfileName, chfileInfo, parameters
            )
            print(
                "\n #",
                fileCount,
                " Down Sampled Output File Location: ",
                output_path,
                "\n Time to Downsample: ",
                totTime,
            )

        fileCount += 1

    return None


if __name__ == "__main__":
    try:
        drive_letter = sys.argv[1]
        folder = ""
        if len(sys.argv) > 2:
            for arg in sys.argv[2:]:
                folder += arg + " "
        folder = folder.strip()
        os.path.normpath(folder)
        print(
            "Exporting the channel bois from the folder: ",
            folder,
            " in drive: ",
            drive_letter,
            "\n",
        )
        run(drive_letter, folder)
        alert("Downsample completed!")
    except Exception as e:
        print("Error: ", e)
        alert("Downsample failed!")
