from inspect import signature
import tempfile
import os
import logging
import subprocess
import shutil
import glob
import pathlib
import hashlib
from aws_cdk import (
    core,
    aws_dynamodb,
    aws_events,
    aws_apigateway,
    aws_lambda,
    aws_logs,
    aws_s3,
    aws_sqs,
    aws_events_targets)


def gen_name(scope: core.Construct, id: str):
    stack = [_ for _ in scope.node.scopes if core.Stack.is_stack(_)][0]
    return f"{stack.stack_name}-{id}"


def get_params(allvars: dict) -> dict:
    """
    Filters all parameters that are KEYWORD_ONLY from allvars (retrieved by locals()),
    combines them with kwargs (found in allvars) and returns the resulting dict.

    This helps getting all the parameters to a function (e.g. __init__)
    into a dictionary to handle them uniformly.

    Parameters in the global list non_passthrough_names will NOT be included in the result.
    This avoids passing those parameters to super.__init__(..., **kwargs)

    Example usage:
    >>>class foo():
    ...   def __init__(self, a, b, *, c=3, d=4, **kwargs):
    ...      print(get_params(locals()))
    >>>foo("a", "b", d="DDD", foobar="baz")
    {c: 3, d: "DDD", foobar: "baz"}

    :param locals: Dictionary with local variables
    :return: Combined dictionary
    """
    assert(allvars.get("self"))
    assert("kwargs" in allvars)
    kwargs = allvars.get("kwargs")
    if not kwargs:
        kwargs = {}
    cls = type(allvars["self"])
    parameters = signature(cls.__init__).parameters
    return {**{k: v for (k, v) in allvars.items()
            if parameters.get(k)
            and parameters[k].kind == parameters[k].KEYWORD_ONLY}, **kwargs}


def filter_kwargs(kwargs: dict, filter: str) -> dict:
    """
    Filter the dictionary including only keys starting with filter.
    The resulting dictionary will have the filter string removed from the keys.

    :param kwargs: Dictionary to filter
    :param filter: string to filter on
    :return: Filtered dictionary with renamed keys

    Example:
    >>>d = {"a_b": 1, "a_c": 2, "b_abc": "abc"}
    >>>print(filter_kwargs(d, "a_"))
    {'b': 1, 'c': 2}
    >>>print(filter_kwargs(d, "b_"))
    {'abc': 'abc'}
    """
    return {k.replace(filter, "", 1): v for (k, v) in kwargs.items() if k.startswith(filter)}


class Function(aws_lambda.Function):
    def __init__(
            self,
            scope: core.Construct,
            id: str,
            *,
            # code=aws_lambda.Code,
            runtime=aws_lambda.Runtime.PYTHON_3_8,
            log_retention=aws_logs.RetentionDays.FIVE_DAYS,
            timeout=core.Duration.seconds(3),
            **kwargs):
        kwargs = get_params(locals())

        kwargs.setdefault('function_name', gen_name(scope, id))
        kwargs.setdefault("handler", f"{id}.main")
        kwargs.setdefault("code", aws_lambda.Code.from_asset(id))

        super().__init__(scope, id, **kwargs)


class Table(aws_dynamodb.Table):
    """
    Creates a DynamoDB table with CDK.

    URL:
    - https://docs.aws.amazon.com/cdk/api/latest/docs/aws-dynamodb-readme.html
    - https://docs.aws.amazon.com/cdk/api/latest/python/aws_cdk.aws_dynamodb/Table.html

    Parameters (extra and those with changed behaviour):
    - table_name (str): gen_name(scope, id) if not set
    """
    def __init__(
            self,
            scope: core.Construct,
            id: str,
            *,
            partition_key=aws_dynamodb.Attribute(
                name='id',
                type=aws_dynamodb.AttributeType.STRING
            ),
            point_in_time_recovery=True,
            removal_policy=core.RemovalPolicy.RETAIN,
            **kwargs):
        kwargs = get_params(locals())

        kwargs.setdefault('table_name', gen_name(scope, id))

        super().__init__(scope, id, **kwargs)


class Queue(aws_sqs.Queue):
    def __init__(
            self,
            scope: core.Construct,
            id: str,
            **kwargs):
        """
        Creates a Queue

        defaults:
        - queue_name - defaults to gen_name(scope, id) if not set.
        """
        kwargs.setdefault('queue_name', gen_name(scope, id))

        super().__init__(scope, id, **kwargs)


class Bucket(aws_s3.Bucket):
    def __init__(
            self,
            scope: core.Construct,
            id: str,
            *,
            block_public_access=aws_s3.BlockPublicAccess.BLOCK_ALL,
            **kwargs):
        """
        Creates an S3 bucket, using some sensible defaults for security.

        See https://docs.aws.amazon.com/cdk/api/latest/python/aws_cdk.aws_s3/Bucket.html
        for a detailed description of parameters.

        - :param bucket_name: defaults to gen_name(scope, id) if not set
        """
        kwargs = get_params(locals())

        # Set the name to a standard
        kwargs.setdefault("bucket_name", gen_name(scope, id).lower())

        super().__init__(scope, id, **kwargs)


class Rule(aws_events.Rule):
    def __init__(
            self,
            scope: core.Construct,
            id: str,
            target: aws_lambda.Function = None,
            **kwargs):
        kwargs = get_params(locals())
        if all([target, kwargs.get("targets")]):
            raise Exception("You may only specify one of 'target' and 'targets")

        if target:
            kwargs.setdefault("targets", [aws_events_targets.LambdaFunction(target)])
        kwargs.setdefault("rule_name", gen_name(scope, id))
        super().__init__(scope, id, **kwargs)


class PipLayers(core.Construct):
    def __init__(
            self,
            scope,
            id, *,
            layers: dict,
            compatible_runtimes=None,
            unpack_dir: str = None,
            **kwargs):
        """
        Create layer using the information in the layers parameter.

        layers is a dictionary containing
           {"id": <path to requirements.txt>, ...}
        a path to a pip-compliant requirements.txt.

        The layers are generated by invoking pip install -r <requirements.txt> -t <dir> and then
        creating a Code.from_asset(<dir>).

        The <dir> will end up under ./.layers.out/<id> (so .layers.out should be added to .gitognore).

        The requirements-file must exist.

        Retrieve the layers via the dictionary <construct>.layers. Typical use would look something like

            lambda_layers = cxs_piplayer.PipLayers(
                self,
                "lambdalayers",
                layers={"utils": "layers/requirements.txt"}).layers

        There is another property, idlayers, containing a dictionary with LayerVersion keyed on id.
        This allows for some granularity when defining layer lists that go to your functions:

            supportlayers = cxs_piplayer.PipLayers(
                self,
                "lambdalayers",
                layers={"utils": "layers/req_utils.txt", "data": "layers/req_data", "dyndb": "layers/req_dyndb.txt"})
            genericlayer = [supportlayers.idlayers["utils"], supportlayers.idlayers["data"]]
            datalayer = [supportlayers.idlayers["data"], supportlayers.idlayers["dyndb"]]

        in case your lambdas require vastly different layer configurations.

        See also
        * https://docs.aws.amazon.com/cdk/api/latest/python/aws_cdk.aws_lambda/LayerVersion.html

        Parameters:
        * :param layers: Dictionary with {"<layer_id>": <path to requirements.txt>, ...}

        * :param compatible_runtimes: defaults to
        [aws_lambda.Runtime.PYTHON_3_6,
        aws_lambda.Runtime.PYTHON_3_7,
        aws_lambda.Runtime.PYTHON_3_8]

        * :param unpack_dir: defaults to "./.layers.out"

        * :raises FileExistsError: Raised if a requirements-file does not exist.
        """
        super().__init__(scope, id)
        if not compatible_runtimes:
            compatible_runtimes = [
                aws_lambda.Runtime.PYTHON_3_6,
                aws_lambda.Runtime.PYTHON_3_7,
                aws_lambda.Runtime.PYTHON_3_8]

        if unpack_dir:
            unpack_dir = pathlib.Path(unpack_dir)
        else:
            curdir = pathlib.Path(os.path.abspath(os.curdir))
            unpack_dir = curdir / ".layers.out"

        if not unpack_dir:
            unpack_dir = pathlib.Path(tempfile.mkdtemp())

        preexisting_packages = self.get_preinstalled_packages(compatible_runtimes)

        self.layers = []
        self.idlayers = {}
        for layer_id, requirements_file in layers.items():
            print(f"Creating layer '{layer_id}'.")
            if not os.path.exists(requirements_file):
                raise FileExistsError(f"Layer {layer_id}: '{requirements_file}' does not exist.")

            layer_unpack_dir = unpack_dir / layer_id
            unpack_to_dir = layer_unpack_dir / "python"
            with open(requirements_file) as f:
                req_md5 = hashlib.md5(f.read().encode()).hexdigest()
            prev_md5 = None
            if layer_unpack_dir.exists() and (layer_unpack_dir / "md5sum").exists():
                with open(layer_unpack_dir / "md5sum") as f:
                    prev_md5 = f.read()

            if req_md5 != prev_md5:
                reqs = []
                dev_package = False
                with open(requirements_file) as f:
                    for _ in f.read().splitlines():
                        if _.startswith("-e "):
                            reqs.append( _[3:])
                            dev_package = True
                        else:
                            reqs.append(_)

                tempname = requirements_file
                if dev_package:
                    tempname = tempfile.mktemp()
                    with open(tempname, "w") as f:
                        for _ in reqs:
                            f.write(_ + "\n")

                print(f"Installing {layer_id} to {unpack_to_dir}")
                layer_unpack_dir.mkdir(parents=True, exist_ok=True)
                # Extracting to a subdirectory 'python' as per
                # https://docs.aws.amazon.com/lambda/latest/dg/configuration-layers.html
                pipcommand = f'pip install -r {tempname} -t {unpack_to_dir} --quiet'
                logging.debug(pipcommand)
                logging.debug(open(tempname).readlines())

                try:
                    subprocess.check_output(pipcommand.split())
                except subprocess.CalledProcessError:
                    print("oops")
                    raise

                self.remove_preinstalled_packages(preexisting_packages=preexisting_packages, root_dir=unpack_to_dir)

                with open(layer_unpack_dir / "md5sum", "w") as f:
                    f.write(req_md5)

                if dev_package and os.path.exists(tempname):
                    os.remove(tempname)
            else:
                print(f"Using cached layer image for {layer_id}.")
            code = aws_lambda.Code.from_asset(str(layer_unpack_dir))
            logging.debug(f"Asset path: {code.path}")

            version_id = f"{id}_{layer_id}"
            layer = aws_lambda.LayerVersion(
                scope,
                version_id,
                code=code,
                compatible_runtimes=compatible_runtimes,
                layer_version_name=gen_name(scope, version_id),
                **kwargs)

            self.idlayers[layer_id] = layer
            self.layers.append(layer)

    def get_dir_size(self, root_dir: str) -> int:
        """
        Get the size in bytes of all content under root_dir.

        :param root_dir: Directory node to check size of
        :return: COntent under root_dir in bytes.
        """
        total_size = 0
        for path, dirs, files in os.walk(root_dir):
            for f in files:
                fp = os.path.join(path, f)
                total_size += os.path.getsize(fp)
        return total_size

    def remove_preinstalled_packages(self, *, preexisting_packages: dict, root_dir: str):
        """
        Remove directories containing pre-existing packages.

        :param preexisting_packages: List of pre-exiisting packages
        :param root_dir: Where to delete directories from
        """
        orgsize = self.get_dir_size(root_dir)
        dirs = os.listdir(root_dir)
        for d in dirs:
            # Delete the package directory of it is pre-installed in
            # all runtimes we make the layer for.
            count = 0
            for runtime, packages in preexisting_packages.items():
                if d in packages:
                    count += 1

            if count == len(preexisting_packages):
                fullname = os.path.join(root_dir, d)
                shutil.rmtree(fullname)
                # While we're at it, delete the dist-directory
                auxdirs = glob.glob(f"{fullname}-*")
                for auxdir in auxdirs:
                    shutil.rmtree(auxdir)
                print(f"Removing redundant package {d}.")
        newsize = self.get_dir_size(root_dir)
        sizediff = orgsize - newsize
        print(f"Layer size reduced by {sizediff//(1024*1024)}MB ({100*sizediff/orgsize:.0f}%).")

    def get_preinstalled_packages(self, runtimes: list) -> dict:
        # No need to add thinga already present,
        # using list from https://gist.github.com/gene1wood/4a052f39490fae00e0c3
        res = {}
        curdir = os.path.dirname(__file__)
        # Files cleaned using
        # grep -v "^#" preinstalled_python3.6.txt|awk -F . '{print $1}'|uniq > 3.6.txt

        for runtime in runtimes:
            preinstalled = os.path.join(curdir, f"preinstalled_{runtime.name}.txt")
            if os.path.exists(preinstalled):
                res[runtime.name] = [_.strip() for _ in open(preinstalled).readlines()]
            else:
                logging.warning(f"Could not find {preinstalled}")

        return res


class RestApi(aws_apigateway.RestApi):
    def __init__(
            self,
            scope: core.Construct,
            id: str,
            **kwargs):
        """
        Creates a RestApi with some sensible defaults.

        defaults:
        - rest_api_name -> gen_name(scope, id) if not set
        """
        kwargs.setdefault('rest_api_name', gen_name(scope, id))

        # Set default deploy options
        kwargs.setdefault('deploy_options', aws_apigateway.StageOptions(
            logging_level=aws_apigateway.MethodLoggingLevel.INFO,
            metrics_enabled=True))

        super().__init__(scope, id, **kwargs)

        core.CfnOutput(self, "root_url", value=f"ROOT_URL={self.url}")


class ResourceWithLambda(core.Construct):
    '''
    Construct that wraps the creation of a lambda function,
    optionally a resource and adds a method to the resource
    integrated with the lambda.
    '''
    def __init__(
            self,
            scope: core.Construct,
            id: str, *,
            parent_resource: aws_apigateway.IResource,
            code: aws_lambda.Code = None,
            description: str = None,
            verb: str = "ANY",
            resource_name: str = None,
            integration_request_templates: dict = {"application/json": '{ "statusCode": "200" }'},
            resource_add_child: bool = True,
            **kwargs):
        '''
        Create a lambda function and hook it up to a resource
        with a lambda integration.

        To standardize code, the following defaults are used:

        * function.handler => "{id}.main"

        * function.function_name => "{self.gen_name(f'{id}_handler')}"

        * If resource_name is not set the method will be named {id}

        To simplify passing additional arguments to the sub-parts, any argument
        prefixed with:

        lambda_ -> will be send to the Function constructor

        method_ -> will be sent to add_method()

        integration_ -> will be sent to the integration constructor
        '''
        super().__init__(scope, f"{id}_ResourceWithLambda")
        kwargs = get_params(locals())

        if resource_name and not resource_add_child:
            self.node.add_error(f"{type(self).__name__}('{id}'): Cannot specify both resource_add_child=True and set a resource_name ('{resource_name}').")  # noqa e501

        if not resource_name:
            resource_name = id

        lambda_kwargs = filter_kwargs(kwargs, "lambda_")
        method_kwargs = filter_kwargs(kwargs, "method_")
        integration_kwargs = filter_kwargs(kwargs, "integration_")

        lambda_kwargs.setdefault("function_name", gen_name(scope, f"{id}"))
        lambda_kwargs.setdefault("handler", f"{id}.main")
        if code:
            lambda_kwargs['code'] = code

        # TODO: Wrap this in a canarydeploy. That may be a breaking change unfortunately.
        handler = Function(
            scope,
            f"{id}",
            description=description,
            **lambda_kwargs
        )
        self.handler = handler

        self.integration = aws_apigateway.LambdaIntegration(self.handler, **integration_kwargs)

        if resource_add_child:
            self.resource = parent_resource.add_resource(resource_name)
        else:
            self.resource = parent_resource
        self.method = self.resource.add_method(verb, self.integration, **method_kwargs)
        core.CfnOutput(
            self,
            f"{id}_url",
            value=f"{id}:: {self.resource.url} -- {verb}",
            description=f"url for {id}")
