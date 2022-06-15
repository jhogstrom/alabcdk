# Helper constructs for CDK

CDK offers an object oriented approach to Infrastructure as Code. This means it is also possible to create specialized subclasses or aggregates.

This set of constructs adds useful functionality to commonly used infrastructure pieces. It also plays nicely with the way we develop software internally at Aditro Logistics, by adding stack meta data with names that should not be hard coded in lambda functions.

# Add to project
Use it by adding the following line to your top level `requirements.txt`:

```
git+https://github.com/aditrologistics/alabcdk.git
```

You should always use a **virtual environment**.
```
python -m venv .venv
```


## Dependencies
This package requires most of the aws packages. Hence they will be automatically included when you install this package.

# Usage
The constructs are available after specifying `import alabcdk` in your python code.

Since this is a deployment only tool set, there is no need to deploy it with your lambda functions for instance.

# Documentation
The code is documented inline. Full documentation for all CDK constructs can be found in the official CDK documentation.