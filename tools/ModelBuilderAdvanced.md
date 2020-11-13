# Model Builder - Advanced

This document provides details and information on more advanced usages
of the [model-builder script](/tools/scripts/model-builder). For
basic usage instructions, see the [README.md](README.md) file.

## Custom Settings

There are environment variables that can be set prior to running the
model-builder script in order provide custom settings for the model
packages and containers.

| Variable | Default value | Description |
|----------|---------------|-------------|
| `MODEL_PACKAGE_DIR` | `../output` | Directory where model package .tar.gz files are located |
| `LOCAL_REPO` | `model-zoo` | Local images will be built as `${LOCAL_REPO}:tag`. Tags are defined by the spec yml files |
| `TENSORFLOW_TAG` | `2.3.0-ubuntu-18.04` | Tag of the intel-optimized-tensorflow image to use as the base for versioned containers |
| `TAG_PREFIX` | `${TENSORFLOW_TAG}` | Prefix used for the image tags (typically this will be the TF version) |
| `MODEL_WORKSPACE` | `/workspace` | Location where the model package will be extracted in the model container |
| `IMAGE_LIST_FILE` | None | Specify a file path where the list of built image/tags will be written. This is used by automated build scripts. |

You can set these environment variables to customize the model-builder
settings. For example:

```
MODEL_PACKAGE_DIR=/tmp/model_packages model-builder
```

## Documentation text replacement

When `init-spec` is run, model spec yaml file's documentation section has
a `text_replace` dictionary that defines keyword and value pairs that
will be replaced when the final README.md is generated. The final README.md
can be generated using either `model-builder generate-documentation <model>`
or `model-builder make <model>`. The `text_replace` section is _optional_,
and if it doesn't exist then no text replacement will happen when
documentation is generated.

By default, when `init-spec` is run, the following text replacement
options will be defined in the model's spec yaml file:

| Keyword | Value |
|---------|-------|
| `<model name>` | The model's name formatted to be written in sentences (like `ResNet50` or `SSD-MobileNet`) |
| `<precision>` | The model's precision formatted to be written in sentences (like `FP32` or `Int8`) |
| `<mode>` | The mode for the model package/container (`inference` or `training`)
| `<use_case>` | The model's use case formatted as it is in the model zoo directory structure (like `image_recognition` or `object_detection`) |
| `<model-precision-mode>` | The model spec name, which consists of the model name, precision, and mode, as it's formatted in file names (like `resnet50-fp32-inference`) |

An example of what this looks like in the spec yaml is below:
```
    documentation:
        ...
        text_replace:
            <mode>: inference
            <model name>: SSD-ResNet34
            <precision>: FP32
            <use case>: object_detection
            <package url>:
            <package name>: ssd-resnet34-fp32-inference.tar.gz
            <package dir>: ssd-resnet34-fp32-inference
            <docker image>:
```

> Note: Please make sure to fill in the package url and docker image
> once the they have been uploaded and pushed to a repo.

After `init-spec` is run, these values can be changed (for example, if
the `<model name>` is not formatted correctly).

The [documentation fragments](/tools/docker/docs) use the keywords.
For example, [title.md](/tools/docker/docs/title.md) has:
```
<!--- 0. Title -->
# <model name> <precision> <mode>
```

When the documentation is generated, the text subsitution will happen and
the generated README.md will have the values filled in:
```
<!--- 0. Title -->
# SSD-ResNet34 FP32 inference
```

## Release Group

The `--release-group <group name>` (or `-r`) flag to the `model-builder` script
refers to the `releases` section in the spec yml files and is passed to
the [assembler.py](/tools/docker/assembler.py) `release` flag by the
model-builder. For example, the ResNet50 v1.5 spec yml lists it using
the `versioned` and `dockerfiles` release groups
[here](/tools/docker/specs/resnet50v1-5-fp32-inference_spec.yml#L1-L7).
Containers in a release group are built together since they use a common
set of build arguments (such as the framework version and tag prefix).
The `dockerfiles` release group will always be used when constructing
dockerfiles.

The `--release-group` (or `-r`) flag applies to the following model-builder subcommands:
* make (e.g. `model-builder make -r versioned resnet50-fp32-inference`) - for the `build` step only
* build (e.g `model-builder build -r ml xgboost`)
* images (e.g `model-builder images -r versioned` or `model-builder images -r ml`)

Multiple release group flags can be listed to have the command apply to
multiple groups. For example: `model-builder build -r versioned -r tf_1.15.2_containers all`.

> If no `--release-group <group name>` (or `-r`) flag is passed to the
> `model-builder`, the default behavior will be to use the TensorFlow
> release groups.

## Under the hood of the subcommands

### Building packages

The model-builder command will build packages by calling docker run on the imz-tf-tools container passing
in arguments to assembler.py. This internal call looks like the following:

```
docker run --rm -u 503:20 -v <path-to-models-repo>/tools/docker:/tf -v $PWD:/tf/models imz-tf-tools python3 assembler.py --release dockerfiles --build_packages --model_dir=models --output_dir=models/output
```

For single targets such as `bert-large-fp32-training` the model-builder adds an argument:

```
--only_tags_matching=.*bert-large-fp32-training$
```

### Constructing Dockerfiles

The model-builder command will construct Dockerfiles by calling docker run on the imz-tf-tools container passing
in arguments to assembler.py. This internal call looks like the following:

```
docker run --rm -u 503:20 -v <path-to-models-repo>/tools/docker:/tf -v <path-to-models-repo>/dockerfiles:/tf/dockerfiles imz-tf-tools python3 assembler.py --release dockerfiles --construct_dockerfiles
```

For single targets such as `bert-large-fp32-training` the model-builder adds an argument:

```
--only_tags_matching=.*bert-large-fp32-training$
```

### Building images

The model-builder command will build images by calling docker run on the imz-tf-tools container passing
in arguments to assembler.py. This internal call looks like the following:

```
docker run --rm -v <path-to-models-repo>/tools/docker:/tf -v /var/run/docker.sock:/var/run/docker.sock imz-tf-tools python3 assembler.py --arg _TAG_PREFIX=2.3.0 --arg http_proxy= --arg https_proxy= --arg TENSORFLOW_TAG=2.3.0-ubuntu-18.04 --arg PACKAGE_DIR=model_packages --arg MODEL_WORKSPACE=/workspace --repository model-zoo --release versioned --build_images --only_tags_matching=.*bert-large-fp32-training$ --quiet
```

For single targets such as `bert-large-fp32-training` the model-builder adds an argument:

```
--only_tags_matching=.*bert-large-fp32-training$
```
