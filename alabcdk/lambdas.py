import pathlib
import hashlib
import os
import tempfile
import logging
import subprocess
import shutil
import glob
from typing import List, Optional
from constructs import Construct
from aws_cdk import (
    Duration,
    aws_lambda,
    aws_logs
)
from .utils import (gen_name, get_params, generate_output, setup_logger)

logger = setup_logger(name="alabcdk")
_stage_to_loglevel = {
    "PROD": "INFO",
    "TEST": "DEBUG",
    "DEV": "DEBUG"
}


_DEFAULT_LAMBDA_LOGLEVEL = "DEBUG"
class Function(aws_lambda.Function):
    def _loglevel_for_stage(self) -> str:
        stage = "DEV"
        if hasattr(self.stack, "stage"):
            stage = self.stack.stage
        return _stage_to_loglevel.get(stage, _DEFAULT_LAMBDA_LOGLEVEL)

    def __init__(
            self,
            scope: Construct,
            id: str,
            *,
            # code=aws_lambda.Code,
            runtime=aws_lambda.Runtime.PYTHON_3_9,
            log_retention=aws_logs.RetentionDays.FIVE_DAYS,
            timeout=Duration.seconds(3),
            **kwargs):
        kwargs = get_params(locals())

        kwargs.setdefault('function_name', gen_name(scope, id))
        kwargs.setdefault("handler", f"{id}.main")
        kwargs.setdefault("code", aws_lambda.Code.from_asset(id, exclude=[".env*"]))

        super().__init__(scope, id, **kwargs)

        for k, v in kwargs.get("environment", {}).items():
            generate_output(self, k, v)

        self.add_environment("LOGLEVEL", self._loglevel_for_stage())

    def add_environment(self, key: str, value: str, *, remove_in_edge: Optional[bool] = None) -> "Function":
        generate_output(self, key, value)
        return super().add_environment(key, value, remove_in_edge=remove_in_edge)


class PipLayers(Construct):
    def cleaned_requirements(self, filename) -> str:
        """
        Clean up requirements.txt file and return a name to clean file.
        """
        reqs = []
        dev_package = False
        with open(filename) as f:
            for _ in f.read().splitlines():
                if _.startswith("-e "):
                    reqs.append(_[3:])
                    dev_package = True
                else:
                    reqs.append(_)

        if not dev_package:
            return filename
        logger.debug("Writing a new file, as it contains -e packages")

        if dev_package:
            tempname = tempfile.mktemp()
            with open(tempname, "w") as f:
                for _ in reqs:
                    f.write(_ + "\n")
        return tempname

    def __init__(
            self,
            scope,
            id, *,
            layers: dict,
            compatible_runtimes=None,
            unpack_dir: str = None,
            force_exclude_packages: List[str] = None,
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
        [aws_lambda.Runtime.PYTHON_3_8,
        aws_lambda.Runtime.PYTHON_3_9

        * :param unpack_dir: defaults to "./.layers.out"

        * :raises FileExistsError: Raised if a requirements-file does not exist.
        """
        super().__init__(scope, id)
        if not compatible_runtimes:
            compatible_runtimes = [
                aws_lambda.Runtime.PYTHON_3_8,
                aws_lambda.Runtime.PYTHON_3_9]

        if unpack_dir:
            unpack_dir = pathlib.Path(unpack_dir)
        else:
            curdir = pathlib.Path(os.path.abspath(os.curdir))
            unpack_dir = curdir / ".layers.out"

        if not unpack_dir:
            unpack_dir = pathlib.Path(tempfile.mkdtemp())

        self.force_exclude_packages = force_exclude_packages or []

        preexisting_packages = None

        self.layers = []
        self.idlayers = {}
        for layer_id, requirements_file in layers.items():
            logger.info(f"Creating layer '{layer_id}'.")
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
                preexisting_packages = preexisting_packages or self.get_preinstalled_packages(compatible_runtimes)


                tempname = self.cleaned_requirements(requirements_file)

                logger.info(f"Installing {layer_id} to {unpack_to_dir}")
                layer_unpack_dir.mkdir(parents=True, exist_ok=True)
                # Extracting to a subdirectory 'python' as per
                # https://docs.aws.amazon.com/lambda/latest/dg/configuration-layers.html
                pipcommand = f'pip install -r {tempname} -t {unpack_to_dir} --quiet'
                logger.debug(pipcommand)
                logger.debug(open(tempname).readlines())

                try:
                    subprocess.check_output(pipcommand.split())
                except subprocess.CalledProcessError as e:
                    logger.error("oops", e)
                    raise

                self.remove_preinstalled_packages(
                    preexisting_packages=preexisting_packages,
                    root_dir=unpack_to_dir)

                with open(layer_unpack_dir / "md5sum", "w") as f:
                    f.write(req_md5)

                if tempname != requirements_file and os.path.exists(tempname):
                    os.remove(tempname)
            else:
                logger.info(f"Using cached layer image for {layer_id}.")
            code = aws_lambda.Code.from_asset(str(layer_unpack_dir))
            logger.debug(f"Asset path: {code.path}")

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
        :return: Content under root_dir in bytes.
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

        :param preexisting_packages: dict of pre-existing packages keyed by
            runtime name and vaklue is a list of packages.
        :param root_dir: Where to delete directories from.
        """
        orgsize = self.get_dir_size(root_dir)
        dirs = os.listdir(root_dir)
        for d in dirs:
            # Delete the package directory of it is pre-installed in
            # all runtimes we make the layer for.
            count = 0
            for runtime, packages in preexisting_packages.items():
                if d in packages:
                    # logger.debug(f">> {d} found in {runtime}")
                    count += 1
                # else:
                #     logger.debug(f"-- {d} NOT found in {runtime}")

            if count == len(preexisting_packages) or d in self.force_exclude_packages:
                fullname = os.path.join(root_dir, d)
                shutil.rmtree(fullname)
                # While we're at it, delete the dist-directory
                auxdirs = glob.glob(f"{fullname}-*")
                for auxdir in auxdirs:
                    logger.debug(f"Deleting {auxdir}")
                    shutil.rmtree(auxdir)
                if d in self.force_exclude_packages:
                    reason = "excluded by request"
                else:
                    reason = "pre-installed"
                logger.info(f"Removing redundant package {d} ({reason}).")
            else:
                logger.debug(f"Keeping {d}: preinstalled in {count}/{len(preexisting_packages)} runtimes.")
        newsize = self.get_dir_size(root_dir)
        sizediff = orgsize - newsize
        logger.info(f"Layer size reduced by {sizediff//(1024*1024)}MB ({100*sizediff/orgsize:.0f}%).")
        logger.info(f"Final layer size {(orgsize - sizediff)//(1024*1024)}MB")

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
                res[runtime.name] = [_.strip() for _ in open(preinstalled).readlines() if _.strip() != ""]
                logger.info(f"Loading and comparing with {len(res[runtime.name])} packages in '{preinstalled}'.")
                # for _ in res[runtime.name]:
                #     logger.debug(f">> {runtime.name}: {_}")
            else:
                logger.warning(f"Could not find file '{preinstalled}'.")

        return res
