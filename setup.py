import setuptools

long_description = """Brython's Turtle module port to Basthon project."""

setuptools.setup(
    name="turtle",
    version="0.0.1",
    author="Romain Casati",
    author_email="Romain.Casati@basthon.fr",
    description=long_description,
    long_description=long_description,
    url="https://forge.apps.education.fr/basthon/basthon-kernel/",
    packages=setuptools.find_packages(),
    license="GPL-3.0-or-later",
    classifiers=[
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Interpreters",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
    ],
    python_requires=">=3.4",
)
