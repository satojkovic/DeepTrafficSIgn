# The MIT License (MIT)
# Copyright (c) 2018 satojkovic

# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:

# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

#!/usr/bin/env python
# -*- coding: utf-8 -*-

import cv2
import os
import pandas as pd
import re
import joblib
import numpy as np
import model_sof as model
import common


def gt_csv_getline(gt_csvs):
    for gt_csv in gt_csvs:
        df = pd.io.parsers.read_csv(gt_csv, delimiter=';', skiprows=0)
        n_lines = df.shape[0]
        for i in range(n_lines):
            img_file_path = os.path.join(
                os.path.dirname(gt_csv), df.loc[i, 'Filename'])
            # bbox include (Width;Height;Roi.X1;Roi.Y1;Roi.X2;Roi.Y2)
            bbox = {
                'Width': df.loc[i, 'Width'],
                'Height': df.loc[i, 'Height'],
                'Roi.X1': df.loc[i, 'Roi.X1'],
                'Roi.Y1': df.loc[i, 'Roi.Y1'],
                'Roi.X2': df.loc[i, 'Roi.X2'],
                'Roi.Y2': df.loc[i, 'Roi.Y2']
            }
            classId = df.loc[i, 'ClassId']
            yield (img_file_path, bbox, classId)


def get_gt_csvs(root_dir):
    gt_csvs = [
        os.path.join(root, f)
        for root, dirs, files in os.walk(root_dir) for f in files
        if re.search(r'.csv', f)
    ]
    return gt_csvs


def parse_gt_csv(gt_csvs, data_size):
    bboxes = np.zeros(
        (data_size, model.IMG_HEIGHT, model.IMG_WIDTH, model.IMG_CHANNELS),
        dtype=np.uint8)
    classIds = np.zeros((data_size, 1), dtype=np.int32)
    for i, (img_file_path, bbox,
            classId) in enumerate(gt_csv_getline(gt_csvs)):
        # Crop ground truth bounding box
        img = cv2.imread(img_file_path)
        gt_bbox = img[bbox['Roi.Y1']:bbox['Roi.Y2'], bbox['Roi.X1']:bbox[
            'Roi.X2']]

        # Resize to same size
        gt_bbox = cv2.resize(gt_bbox, (model.IMG_WIDTH, model.IMG_HEIGHT))

        # Expand dimension to stack image arrays
        gt_bbox = np.expand_dims(gt_bbox, axis=0)

        # Append bbox and classId
        bboxes[i] = gt_bbox
        classIds[i] = classId
    return bboxes, classIds


def save_as_pickle(train_or_test, bboxes, classIds, pkl_fname, shuffle=False):
    if shuffle:
        shuffled_idx = np.random.permutation(len(bboxes))
        save_bboxes = np.array(bboxes)[shuffled_idx]
        save_classIds = np.array(classIds)[shuffled_idx]
    else:
        save_bboxes = np.array(bboxes)
        save_classIds = np.array(classIds)

    if train_or_test == 'train':
        save = {'train_bboxes': save_bboxes, 'train_classIds': save_classIds}
    else:
        save = {'test_bboxes': save_bboxes, 'test_classIds': save_classIds}
    joblib.dump(save, pkl_fname, compress=5)


def preproc(bboxes, classIds):
    preproced_bboxes = np.zeros(bboxes.shape)

    # Histogram equalization on color image
    for i, bbox in enumerate(bboxes):
        img = cv2.cvtColor(bbox, cv2.COLOR_BGR2YCrCb)
        split_img = cv2.split(img)
        split_img[0] = cv2.equalizeHist(split_img[0])
        eq_img = cv2.merge(split_img)
        eq_img = cv2.cvtColor(eq_img, cv2.COLOR_YCrCb2BGR)

        # Scaling in [0, 1]
        eq_img = (eq_img / 255.).astype(np.float32)

        # Append bboxes
        preproced_bboxes[i] = eq_img
    return preproced_bboxes, classIds


def aug_by_flip(bboxes, classIds):
    aug_bboxes = np.zeros(
        (0, bboxes.shape[1], bboxes.shape[2], bboxes.shape[3]), dtype=np.uint8)
    aug_classIds = np.zeros((0, classIds.shape[1]), dtype=np.int32)
    n_classes = model.NUM_CLASSES

    # This classification is referenced to below.
    # https://navoshta.com/traffic-signs-classification/
    #
    # horizontal flip class
    hflip_cls = np.array([11, 12, 13, 15, 17, 18, 22, 26, 30, 35])
    # vertical flip class
    vflip_cls = np.array([1, 5, 12, 15, 17])
    # hozirontal and then vertical flip
    hvflip_cls = np.array([32, 40])
    # horizontal flip but the class change
    hflip_cls_changed = np.array([
        [19, 20],
        [33, 34],
        [36, 37],
        [38, 39],
        [20, 19],
        [34, 33],
        [37, 36],
        [39, 38],
    ])

    for c in range(n_classes):
        idxes = np.where(classIds == c)[0]
        src = bboxes[idxes]
        srcIds = classIds[idxes]

        if c in hflip_cls:
            # list of images(Ids) that flipped horizontally
            dst = src[:, ::-1, :, :]
            # append to bbox and classIds
            aug_bboxes = np.append(aug_bboxes, dst, axis=0)
            aug_classIds = np.append(aug_classIds, srcIds, axis=0)
        if c in vflip_cls:
            # list of images(Ids) that flipped vertically
            dst = src[:, :, ::-1, :]
            # append to bbox and classIds
            aug_bboxes = np.append(aug_bboxes, dst, axis=0)
            aug_classIds = np.append(aug_classIds, srcIds, axis=0)
        if c in hvflip_cls:
            # list of images(Ids) that flipped horizontally and vertiaclly
            dst = src[:, ::-1, :, :]
            dst = dst[:, :, ::-1, :]
            # append to bbox and classIds
            aug_bboxes = np.append(aug_bboxes, dst, axis=0)
            aug_classIds = np.append(aug_classIds, srcIds, axis=0)
        if c in hflip_cls_changed[:, 0]:
            dst = src[:, ::-1, :, :]
            dstIds = np.asarray([
                hflip_cls_changed[hflip_cls_changed[:, 0] == c][0][1]
                for i in range(len(srcIds))
            ])
            # append to bbox and classIds
            aug_bboxes = np.append(aug_bboxes, dst, axis=0)
            aug_classIds = np.append(
                aug_classIds, np.expand_dims(dstIds, axis=1), axis=0)
    return np.append(bboxes, aug_bboxes, axis=0), \
        np.append(classIds, aug_classIds, axis=0)


def main():
    train_gt_csvs = get_gt_csvs(common.TRAIN_ROOT_DIR)
    test_gt_csvs = get_gt_csvs(common.TEST_ROOT_DIR)

    train_bboxes, train_classIds = parse_gt_csv(train_gt_csvs,
                                                common.TRAIN_SIZE)
    test_bboxes, test_classIds = parse_gt_csv(test_gt_csvs, common.TEST_SIZE)
    print('train dataset {}, labels {}'.format(train_bboxes.shape,
                                               train_classIds.shape))
    print('test dataset {}, labels {}'.format(test_bboxes.shape,
                                              test_classIds.shape))

    # Preprocessing and apply data augmentation method
    train_bboxes, train_classIds = preproc(train_bboxes, train_classIds)
    print('train dataset(after preprocessing) {}, labels {}'.format(
        train_bboxes.shape, train_classIds.shape))

    # flip
    train_bboxes, train_classIds = aug_by_flip(train_bboxes, train_classIds)
    print(
        'train dataset(after data augmentation) {}'.format(len(train_bboxes)))

    # Convert classIds to one hot vector
    train_one_hot_classIds = np.eye(
        model.NUM_CLASSES)[train_classIds.reshape(len(train_classIds))]
    test_one_hot_classIds = np.eye(
        model.NUM_CLASSES)[test_classIds.reshape(len(test_classIds))]

    # Save bboxes and classIds as pickle
    save_as_pickle(
        'train',
        train_bboxes,
        train_one_hot_classIds,
        common.TRAIN_PKL_FILENAME,
        shuffle=True)
    save_as_pickle('test', test_bboxes, test_one_hot_classIds,
                   common.TEST_PKL_FILENAME)


if __name__ == '__main__':
    main()
