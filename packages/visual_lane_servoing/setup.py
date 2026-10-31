import os
from glob import glob

from setuptools import setup

package_name = "visual_lane_servoing"

setup(
    name=package_name,
    version="2.0.0",
    # `include/` holds the student code (visual_servoing_solution.py); the node imports it as
    # `visual_lane_servoing.include` (see visual_lane_servoing/__init__.py), the same name the notebooks use
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
        (os.path.join("share", package_name, "config", "vls_node"), glob("config/vls_node/*.yaml")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Liam P",
    maintainer_email="liam@duckietown.com",
    description="The package performs visual servoing on lanes.",
    license="GPLv3",
    entry_points={
        "console_scripts": [
            "visual_lane_servoing_node = visual_lane_servoing.visual_lane_servoing_node:main",
        ],
    },
)
