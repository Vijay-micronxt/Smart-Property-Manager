from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

setup(
    name="property_core",
    version="0.0.1",
    description="Property Lifecycle Core App for ERPNext",
    author="Smart Property Manager",
    author_email="admin@smartproperty.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
