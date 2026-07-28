from setuptools import setup, find_packages

with open("property_core/requirements.txt") as f:
    install_requires = [line.strip() for line in f if line.strip() and not line.startswith("#")]

setup(
    name="property_core",
    version="0.0.1",
    description="Smart Property Manager — Property Core for ERPNext",
    author="Smart Property Manager",
    author_email="admin@smartproperty.com",
    packages=find_packages(where="property_core"),
    package_dir={"": "property_core"},
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
