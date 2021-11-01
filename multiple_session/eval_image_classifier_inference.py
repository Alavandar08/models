#
# -*- coding: utf-8 -*-
#
# Copyright (c) 2018 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

#

# used to load timeline format for chrome trace
from tensorflow.python.client import timeline


import time
from argparse import ArgumentParser

import tensorflow as tf
from tensorflow.python.tools.optimize_for_inference_lib import optimize_for_inference
from tensorflow.python.framework import dtypes

import datasets
import numpy as np

INPUTS = 'input'
OUTPUTS = 'predict'

INCEPTION_V3_IMAGE_SIZE = 299


class eval_classifier_optimized_graph:
  """Evaluate image classifier with optimized TensorFlow graph"""

  def __init__(self):

    arg_parser = ArgumentParser(description='Parse args')

    arg_parser.add_argument('-b', "--batch-size",
                            help="Specify the batch size. If this " \
                                 "parameter is not specified or is -1, the " \
                                 "largest ideal batch size for the model will " \
                                 "be used.",
                            dest="batch_size", type=int, default=-1)

    arg_parser.add_argument('-e', "--num-inter-threads",
                            help='The number of inter-thread.',
                            dest='num_inter_threads', type=int, default=0)

    arg_parser.add_argument('-a', "--num-intra-threads",
                            help='The number of intra-thread.',
                            dest='num_intra_threads', type=int, default=0)

    arg_parser.add_argument('-g', "--input-graph",
                            help='Specify the input graph for the transform tool',
                            dest='input_graph')

    arg_parser.add_argument('-d', "--data-location",
                            help='Specify the location of the data. '
                                 'If this parameter is not specified, '
                                 'the benchmark will use random/dummy data.',
                            dest="data_location", default=None)

    arg_parser.add_argument('-r', "--accuracy-only",
                            help='For accuracy measurement only.',
                            dest='accuracy_only', action='store_true')

    arg_parser.add_argument("--warmup-steps", type=int, default=10,
                            help="number of warmup steps")
    arg_parser.add_argument("--steps", type=int, default=50,
                            help="number of steps")

    arg_parser.add_argument(
      '--data-num-inter-threads', dest='data_num_inter_threads',
      help='number threads across operators',
      type=int, default=16)
    arg_parser.add_argument(
      '--data-num-intra-threads', dest='data_num_intra_threads',
      help='number threads for data layer operator',
      type=int, default=14)
    arg_parser.add_argument(
      '--num-cores', dest='num_cores',
      help='number of cores',
      type=int, default=28)

    self.args = arg_parser.parse_args()

    # validate the arguments specific for InceptionV3
    self.validate_args()

  def run(self):
    """run benchmark with optimized graph"""

    print("Run inference")

    data_config = tf.compat.v1.ConfigProto()
    data_config.intra_op_parallelism_threads = self.args.data_num_intra_threads
    data_config.inter_op_parallelism_threads = self.args.data_num_inter_threads
    data_config.use_per_session_threads = 1


    infer_config_inc = tf.compat.v1.ConfigProto()
    infer_config_inc.intra_op_parallelism_threads = self.args.num_intra_threads
    infer_config_inc.inter_op_parallelism_threads = 1
    infer_config_inc.use_per_session_threads = 1


    infer_config_seq = tf.compat.v1.ConfigProto()
    infer_config_seq.intra_op_parallelism_threads = 64
    infer_config_seq.inter_op_parallelism_threads = 1
    infer_config_seq.use_per_session_threads = 1



    data_graph = tf.Graph()
    with data_graph.as_default():
      if (self.args.data_location):
        print("Inference with real data.")
        dataset = datasets.ImagenetData(self.args.data_location)
        preprocessor = dataset.get_image_preprocessor()(
          INCEPTION_V3_IMAGE_SIZE, INCEPTION_V3_IMAGE_SIZE, self.args.batch_size,
          num_cores=self.args.num_cores,
          resize_method='bilinear')
        images, labels = preprocessor.minibatch(dataset, subset='validation')
      else:
        print("Inference with dummy data.")
        input_shape = [self.args.batch_size, INCEPTION_V3_IMAGE_SIZE, INCEPTION_V3_IMAGE_SIZE, 3]
        images = tf.random.uniform(input_shape, 0.0, 255.0, dtype=tf.float32, name='synthetic_images')
    
    
    # define where to cut the graphs
    cuts = [
    [['input'],['v0/cg/mpool1/MaxPool','output node name']],
    [['v0/cg/mpool1/MaxPool'],['v0/cg/incept_v3_a0/concat']],
    [['v0/cg/incept_v3_a0/concat'],['predict']],
    ]
    
    #get number of graphs
    number_of_graphs=len(cuts)
    infer_graphs=[]
    graph_def = tf.compat.v1.GraphDef()
    with tf.compat.v1.gfile.FastGFile(self.args.input_graph, 'rb') as input_file:
      input_graph_content = input_file.read()
      graph_def.ParseFromString(input_graph_content)

      output_graph = optimize_for_inference(graph_def,cuts, dtypes.float32.as_datatype_enum, False)
    
    # assign each cut graph into a list of graph object
    for i in range(number_of_graphs):
        infer_graphs.append(tf.Graph())
        with infer_graphs[i].as_default():
            tf.import_graph_def(output_graph[i], name='')
        
        #write each graph for debugging
        tf.io.write_graph(output_graph[i], './', 'check'+str(i)+'.pb', as_text=False)

    data_sess  = tf.compat.v1.Session(graph=data_graph,  config=data_config)

    # create list of sessions and assign individual graphs objects to it with different inter_op configs
    infer_sessions =[]
    for i in range(number_of_graphs):
        if len(cuts[i][0])==1:
            infer_sessions.append(tf.compat.v1.Session(graph=infer_graphs[i], config=infer_config_seq))
        else:
            infer_sessions.append(tf.compat.v1.Session(graph=infer_graphs[i], config=infer_config_inc))
    
    num_processed_images = 0
    num_remaining_images = datasets.IMAGENET_NUM_VAL_IMAGES

    if (not self.args.accuracy_only):
      iteration = 0
      warm_up_iteration = self.args.warmup_steps
      total_run = self.args.steps
      total_time = 0
              
      #tracing 
      options = tf.compat.v1.RunOptions(trace_level=tf.compat.v1.RunOptions.FULL_TRACE)
      # option to get metadata of trace
      run_metadata = tf.compat.v1.RunMetadata()

      while num_remaining_images >= self.args.batch_size and iteration < total_run:
        iteration += 1

        data_load_start = time.time()
        image_np = data_sess.run(images)
        data_load_time = time.time() - data_load_start

        num_processed_images += self.args.batch_size
        num_remaining_images -= self.args.batch_size

        start_time = time.time()
        print('execution started')
        
        total_time_per_graph=[0]*number_of_graphs
        for i in range(number_of_graphs):
            start = time.time()
            # create individual metadata per graph
            # option to get metadata of trace
            run_metadata = tf.compat.v1.RunMetadata()
            if i==0:
                # pass input image and fetch output of first graph
                out = [j+':0' for j in cuts[i][1]]
                intermediate_output = infer_sessions[i].run(out,feed_dict={cuts[i][0][0]+':0':image_np},options=options,run_metadata=run_metadata)
            else:
                # pass previous graphs output and fetch output of current graph
                d = {}
                # input tensors with input assigned to each tensors
                for ind, inp in enumerate(cuts[i][0]):
                    d[inp+':0']=intermediate_output[ind]
                # list of output tensors to fetch
                out = [j+':0' for j in cuts[i][1]]
                intermediate_output = infer_sessions[i].run(out,feed_dict=d,options=options,run_metadata=run_metadata)
                print('done')
            # create timeline object with current graphs run_metadata stats
            trace = timeline.Timeline(run_metadata.step_stats)

            # save chrome trace at iteration 10 for each individual graph
            if iteration==10:
                if (self.args.batch_size == 1):
                    filename = 'trace_inception-v3_Intra-graph-'+str(i)+'.json'
                else:
                    filename = 'trace_inception-v3_Intra-graph-'+str(i)+'.json'
                with open(filename, 'w') as trace_file:
                    # writing timeline object
                    trace_file.write(trace.generate_chrome_trace_format(show_memory=True))

            # calculate time consumed
            time_consumed_per_graph = time.time() - start
            # accumulate time consumed per graph
            total_time_per_graph[i]+=time_consumed_per_graph
        
        time_consume = time.time() - start_time

        # only add data loading time for real data, not for dummy data
        if self.args.data_location:
          time_consume += data_load_time

        print('Iteration %d: %.6f sec' % (iteration, time_consume))
        if iteration > warm_up_iteration:
          total_time += time_consume
      # Create the Timeline object, and write it to a json
      # timeline object
      trace = timeline.Timeline(run_metadata.step_stats)
      total_time_per_graph[:]= [a/(iteration - warm_up_iteration) for a in total_time_per_graph]
      for ind,t in enumerate(total_time_per_graph):
          print('Throughput of graph :'+str(ind)+' (images/sec)   : ', (self.args.batch_size / t))
      
      time_average = total_time / (iteration - warm_up_iteration)
      print('--------------------------------------------------')
      print('Batch size is                : ', self.args.batch_size)
      print('Number of Intra Threads      : ', self.args.num_intra_threads)
      print('Number of Inter Threads      : ', self.args.num_inter_threads)
      print('Benchmark Duration (seconds) :  %.6f' % total_time)
      if (self.args.batch_size == 1):
        print('Latency  (seconds)           : ', time_average)
      print('Throughput is (images/sec)   : ', (self.args.batch_size / time_average))
      print('--------------------------------------------------')
      if (self.args.batch_size == 1):
        filename = 'trace_inception-v3_Intra-'+str(self.args.num_intra_threads)+'_Inter-'+str(self.args.num_inter_threads)+'_Throughput-'+str('%.3f'%(self.args.batch_size / time_average))+'_Latency-'+str('%.3f'%(time_average))+'.json'
      else:
        filename = 'trace_inception-v3_Intra-'+str(self.args.num_intra_threads)+'_Inter-'+str(self.args.num_inter_threads)+'_Throughput-'+str('%.3f'%(self.args.batch_size / time_average))+'.json'
      with open(filename, 'w') as trace_file:
        # writing timeline object
        trace_file.write(trace.generate_chrome_trace_format(show_memory=True))
      
    else:  # accuracy check
      total_accuracy1, total_accuracy5 = (0.0, 0.0)

      while num_remaining_images >= self.args.batch_size:
        # Reads and preprocess data
        np_images, np_labels = data_sess.run([images, labels])
        num_processed_images += self.args.batch_size
        num_remaining_images -= self.args.batch_size

        start_time = time.time()
        # Compute inference on the preprocessed data
        predictions = infer_sess.run(output_tensor,
                                     {input_tensor: np_images})
        elapsed_time = time.time() - start_time
        with tf.Graph().as_default() as accu_graph:
          accuracy1 = tf.reduce_sum(
            input_tensor=tf.cast(tf.nn.in_top_k(predictions=tf.constant(predictions),
                                   targets=tf.constant(np_labels), k=1), tf.float32))

          accuracy5 = tf.reduce_sum(
            input_tensor=tf.cast(tf.nn.in_top_k(predictions=tf.constant(predictions),
                                   targets=tf.constant(np_labels), k=5), tf.float32))
          with tf.compat.v1.Session() as accu_sess:
            np_accuracy1, np_accuracy5 = accu_sess.run([accuracy1, accuracy5])

          total_accuracy1 += np_accuracy1
          total_accuracy5 += np_accuracy5

        print("Iteration time: %0.4f ms" % elapsed_time)
        print("Processed %d images. (Top1 accuracy, Top5 accuracy) = (%0.4f, %0.4f)" \
              % (num_processed_images, total_accuracy1 / num_processed_images,
                 total_accuracy5 / num_processed_images))

  def validate_args(self):
    """validate the arguments"""

    if not self.args.data_location:
      if self.args.accuracy_only:
        raise ValueError("You must use real data for accuracy measurement.")


if __name__ == "__main__":
  evaluate_opt_graph = eval_classifier_optimized_graph()
  evaluate_opt_graph.run()
