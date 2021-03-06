#!/usr/bin/env python

# Copyright 2017 Databricks, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Script to generate TF graphs for DeepImageFeaturizer.
#
# Takes keras models in sparkdl.transformers.keras_applications and prepends reshaping from ImageSchema
# and model specific preprocessing.
# Produces TensorFlow model files and a scala file containing scala wrappers for all the models.
#
# Input (automatic - no need to specify):
#    sparkdl.transformers.keras_applications.KERAS_APPLICATION_MODELS
#
# Output (all in the working directory):
#    1. model *.pb files (need to be uploaded to S3) .
#    2. generated scala model wrappers Models.scala_generated (needs to be moved over to appropriate scala folder)
#

from base64 import b64encode
from hashlib import sha256

import tensorflow as tf
import keras.backend as K

from sparkdl.graph import utils as tfx
from sparkdl.transformers import *
from sparkdl.transformers.keras_applications import *
from sparkdl.transformers.named_image import *

scala_template = """%(license)s
private[sparkdl] object %(name)s extends NamedImageModel {
  override val name = "%(name)s"
  override val height = %(height)d
  override val width = %(width)d
  override val graphInputNode = name + "_input"
  override val graphOutputNode = name + "_sparkdl_output__"

  override def graph: GraphDef = ModelFetcher.getFromWeb(
      "https://s3-us-west-2.amazonaws.com/spark-deep-learning-models/sparkdl-%(name)s_v%(version)d.pb",
      fileName = "sparkdl-inceptionV3_v%(version)d.pb",
      base64Hash = "%(base64)s"
  )
}
"""

def indent(s, lvl):
    return '\n'.join([' '*lvl + x for x in s.split('\n')])

def gen_model(name, license, model, model_file, version=1, featurize=True):
    g = tf.Graph()
    with tf.Session(graph=g) as session:
        K.set_learning_phase(0)
        inTensor = tf.placeholder(dtype=tf.string, shape=[], name="%s_input" % name)
        decoded = tf.decode_raw(inTensor, tf.uint8)
        imageTensor = tf.to_float(
            tf.reshape(
                decoded,
                shape=[
                    1,
                    model.inputShape()[0],
                    model.inputShape()[1],
                    3]))
        m = model.model(preprocessed=model.preprocess(imageTensor), featurize=featurize)
        outTensor = tf.to_double(tf.reshape(m.output, [-1]), name="%s_sparkdl_output__" % name)
        gdef = tfx.strip_and_freeze_until([outTensor], session.graph, session, False)
    g2 = tf.Graph()
    with tf.Session(graph=g2) as session:
        tf.import_graph_def(gdef, name='')
        filename = "sparkdl-%s_v%d.pb" % (name, version)
        print 'writing out ', filename
        tf.train.write_graph(g2.as_graph_def(), logdir="./", name=filename, as_text=False)
        with open("./" + filename, "r") as f:
            h = sha256(f.read()).digest()
            base64_hash = b64encode(h)
            print 'h', base64_hash
    model_file.write(indent(
        scala_template % {
            "license": license,
            "name": name,
            "height": model.inputShape()[0],
            "width": model.inputShape()[1],
            "version": version,
            "base64": base64_hash},2))
    return g2


models_scala_header = """
/*
 * Copyright 2017 Databricks, Inc.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
 
package com.databricks.sparkdl

import java.nio.file.Paths
import org.tensorflow.framework.GraphDef
import com.databricks.sparkdl.DeepImageFeaturizer.NamedImageModel

/**
 * File generated by sparkdl.utils.generate_app_models.
 * Models defined in sparkdl.transformers.keras_applications.py
 */
 
object Models {
 /**
  * A simple test graph used for testing DeepImageFeaturizer.
  */
 private[sparkdl] object TestNet extends NamedImageModel {

    override val name = "_test"
    override val height = 60
    override val width = 40
    override val graphInputNode = "input"
    override val graphOutputNode = "sparkdl_output__"

    override def graph: GraphDef = {
      val file = getClass.getResource("/sparkdl/test_net.pb").getFile
      ModelFetcher.importGraph(Paths.get(file), "jVCEKp1bV53eib8d8OKreTH4fHu/Ji5NHMOsgdVwbMg=")
        .getOrElse {
          throw new Exception(s""\"The hash of file $file did not match the expected value.""\".stripMargin)
        }
    }
  }
"""

inception_license = """
/**
 * Model provided by Keras. All cotributions by Keras are provided subject to the
 * MIT license located at https://github.com/fchollet/keras/blob/master/LICENSE
 * and subject to the below additional copyrights and licenses.
 *
 * Copyright 2016 The TensorFlow Authors.  All rights reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */"""

xception_license = """
/**
 * Model provided by Keras. All cotributions by Keras are provided subject to the
 * MIT license located at https://github.com/fchollet/keras/blob/master/LICENSE.
 */"""

resnet_license = """
/**
 * Model provided by Keras. All cotributions by Keras are provided subject to the
 * MIT license located at https://github.com/fchollet/keras/blob/master/LICENSE
 * and subject to the below additional copyrights and licenses.
 *
 * The MIT License (MIT)
 *
 * Copyright (c) 2016 Shaoqing Ren
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in all
 * copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
 * AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 * SOFTWARE.
 */"""

vgg16_license = """
/**
 * Model provided by Keras. All cotributions by Keras are provided subject to the
 * MIT license located at https://github.com/fchollet/keras/blob/master/LICENSE
 * and subject to the below additional copyrights and licenses.
 *
 * Copyright 2014 Oxford University
 *
 * Licensed under the Creative Commons Attribution License CC BY 4.0 ("License").
 * You may obtain a copy of the License at
 *
 *     https://creativecommons.org/licenses/by/4.0/
 *
 */"""

vgg19_license = vgg16_license

licenses = {"InceptionV3": inception_license, "Xception": xception_license, "ResNet50": resnet_license, "VGG16": vgg16_license, "VGG19": vgg19_license}
if __name__ == '__main__':
    filename = "Models.scala__generated"
    print('generating', filename)
    with open(filename, "w") as f:
        f.write(models_scala_header)
        for name, modelConstructor in sorted(
                keras_applications.KERAS_APPLICATION_MODELS.items(), key=lambda x: x[0]):
            print 'generating model', name
            if not name in licenses:
                raise KeyError("Missing license for model '%s'" % name )
            g = gen_model(license = licenses[name],name=name, model=modelConstructor(), model_file=f)
            print 'placeholders', [x for x in g._nodes_by_id.values() if x.type == 'Placeholder']
        f.write(
            "\n  val _supportedModels = Set[NamedImageModel](TestNet," +
            ",".join(
                keras_applications.KERAS_APPLICATION_MODELS.keys()) +
            ")\n")
        f.write("}\n")
        f.write("\n")
