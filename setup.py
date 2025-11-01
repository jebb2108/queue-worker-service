from setuptools import setup, find_packages

setup(
    name="new_worker_service",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
)