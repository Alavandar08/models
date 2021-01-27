<!--- 40. Quick Start Scripts -->
## Quick Start Scripts

| Script name | Description |
|-------------|-------------|
| [`int8_inference.sh`](int8_inference.sh) | Runs inference on TF records and outputs performance metrics. |
| [`int8_accuracy.sh`](int8_accuracy.sh) | Runs inference and checks accuracy on the results. |
| [`multi_instance_batch_inference.sh`](multi_instance_batch_inference.sh) | A multi-instance run that uses all the cores for each socket for each instance with a batch size of 448 and synthetic data. |
| [`multi_instance_online_inference.sh`](multi_instance_online_inference.sh) | A multi-instance run that uses 4 cores per instance with a batch size of 1. Uses synthetic data if no `DATASET_DIR` is set. |

These quickstart scripts can be run in different environments:
* [Bare Metal](#bare-metal)
* [Docker](#docker)
