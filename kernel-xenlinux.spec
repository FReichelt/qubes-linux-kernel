# A spec file for building xenlinux Dom0 kernel for Qubes
# Based on the Open SUSE kernel-spec & Fedora kernel-spec.
#

#%define _unpackaged_files_terminate_build 0
%define variant xenlinux.qubes
%define rel %(cat rel).%{variant}

%define _buildshell /bin/bash
%define build_flavor xenlinux
%define build_xen	1

%global cpu_arch x86_64
%define cpu_arch_flavor %cpu_arch/%build_flavor

%define kernelrelease %version-%rel.%cpu_arch
%define my_builddir %_builddir/%{name}-%{version}

%define build_src_dir %my_builddir/linux-%version
%define src_install_dir /usr/src/kernels/%kernelrelease
%define kernel_build_dir %my_builddir/linux-obj

%(chmod +x %_sourcedir/{guards,apply-patches,check-for-config-changes})

%define install_vdso 1

Name:           kernel
Summary:        The Xen Kernel
Version:        %{version}
Release:        %{rel}
License:        GPL v2 only
Group:          System/Kernel
Url:            http://www.kernel.org/
AutoReqProv:    on
BuildRequires:  coreutils module-init-tools sparse
Provides:       multiversion(kernel)
Provides:       %name = %version-%kernelrelease

Provides:       kernel-xen-dom0
Provides:       kernel-qubes-dom0
Provides:       kernel-drm-nouveau = 16

Requires:       xen >= 3.4.3
Requires(post): /sbin/new-kernel-pkg
Requires(preun):/sbin/new-kernel-pkg

Requires(pre):  coreutils gawk
Requires(post): dracut

Conflicts:      sysfsutils < 2.0
# root-lvm only works with newer udevs
Conflicts:      udev < 118
Conflicts:      lvm2 < 2.02.33
Provides:       kernel = %version-%kernelrelease

Source0:        linux-%version.tar.bz2
Source14:       series.conf
Source16:       guards
Source17:       apply-patches
Source33:       check-for-config-changes
Source60:       config.sh
Source100:      config-%{build_flavor}
Source200:      patches.arch
Source201:      patches.drivers
Source202:      patches.fixes
Source203:      patches.rpmify
Source204:      patches.suse
Source205:      patches.xen
Source206:      patches.addon
Source207:      patches.kernel.org
Source300:      patches.qubes
BuildRoot:      %{_tmppath}/%{name}-%{version}-build
ExclusiveArch:  x86_64

%description
Qubes Dom0 kernel.

%prep
if ! [ -e %_sourcedir/linux-%version.tar.bz2 ]; then
    echo "The %name-%version.nosrc.rpm package does not contain the" \
	 "complete sources. Please install kernel-source-%version.src.rpm."
    exit 1
fi

SYMBOLS="xen-dom0 xenlinux"

# Unpack all sources and patches
%setup -q -c -T -a 0

mkdir -p %kernel_build_dir

cd linux-%version

%_sourcedir/apply-patches %_sourcedir/series.conf %_sourcedir $SYMBOLS

cd %kernel_build_dir

cp %_sourcedir/config-%{build_flavor} .config

%build_src_dir/scripts/config \
	--set-str CONFIG_LOCALVERSION -%release.%cpu_arch \
	--disable CONFIG_DEBUG_INFO
#	--enable  CONFIG_DEBUG_INFO
# Enabling CONFIG_DEBUG_INFO produces *huge* packages!

MAKE_ARGS="$MAKE_ARGS -C %build_src_dir O=$PWD"
if test -e %_sourcedir/TOLERATE-UNKNOWN-NEW-CONFIG-OPTIONS; then
    yes '' | make oldconfig $MAKE_ARGS
else
    cp .config .config.orig
    make silentoldconfig $MAKE_ARGS < /dev/null
    %_sourcedir/check-for-config-changes .config.orig .config
    rm .config.orig
fi

make prepare $MAKE_ARGS
make scripts $MAKE_ARGS
krel=$(make -s kernelrelease $MAKE_ARGS)

if [ "$krel" != "%kernelrelease" ]; then
    echo "Kernel release mismatch: $krel != %kernelrelease" >&2
    exit 1
fi

make clean $MAKE_ARGS

rm -f source
find . ! -type d -printf '%%P\n' > %my_builddir/obj-files

%build
cd %kernel_build_dir

# If the %jobs macro is defined to a number, make will spawn that many jobs.
# There are several ways how to define it:
# With plain rpmbuild:
#     rpmbuild -ba --define 'jobs N' kernel-$flavor.spec
# To spawn as many jobs as there are cpu cores:
#     rpmbuild -ba --define "jobs 0$(grep -c ^processor /proc/cpuinfo)" \
#         kernel-$flavor.spec
make %{?jobs:-j%jobs} all $MAKE_ARGS CONFIG_DEBUG_SECTION_MISMATCH=y


%install

# get rid of /usr/lib/rpm/brp-strip-debug
# strip removes too much from the vmlinux ELF binary
export NO_BRP_STRIP_DEBUG=true
export STRIP_KEEP_SYMTAB='*/vmlinux-*'

cd %kernel_build_dir

mkdir -p %buildroot/boot
cp -p System.map %buildroot/boot/System.map-%kernelrelease
cp -p arch/x86/boot/vmlinuz %buildroot/boot/vmlinuz-%kernelrelease
cp .config %buildroot/boot/config-%kernelrelease

%if %install_vdso
# Install the unstripped vdso's that are linked in the kernel image
make vdso_install $MAKE_ARGS INSTALL_MOD_PATH=%buildroot
%endif

# Create a dummy initramfs with roughly the size the real one will have.
# That way, rpm will know that this package requires some additional
# space in /boot.
dd if=/dev/zero of=%buildroot/boot/initramfs-%kernelrelease.img \
	bs=1M count=20

gzip -c9 < Module.symvers > %buildroot/boot/symvers-%kernelrelease.gz

make modules_install $MAKE_ARGS INSTALL_MOD_PATH=%buildroot

mkdir -p %buildroot/%src_install_dir

rm -f %buildroot/lib/modules/%kernelrelease/build
rm -f %buildroot/lib/modules/%kernelrelease/source
mkdir -p %buildroot/lib/modules/%kernelrelease/build
(cd %buildroot/lib/modules/%kernelrelease ; ln -s build source)
# dirs for additional modules per module-init-tools, kbuild/modules.txt
mkdir -p %buildroot/lib/modules/%kernelrelease/extra
mkdir -p %buildroot/lib/modules/%kernelrelease/updates
mkdir -p %buildroot/lib/modules/%kernelrelease/weak-updates

pushd %build_src_dir
cp --parents `find  -type f -name "Makefile*" -o -name "Kconfig*"` %buildroot/lib/modules/%kernelrelease/build
cp -a scripts %buildroot/lib/modules/%kernelrelease/build
cp -a --parents arch/x86/include/asm %buildroot/lib/modules/%kernelrelease/build/
cp -a include %buildroot/lib/modules/%kernelrelease/build/include
popd

cp Module.symvers %buildroot/lib/modules/%kernelrelease/build
cp System.map %buildroot/lib/modules/%kernelrelease/build
if [ -s Module.markers ]; then
cp Module.markers %buildroot/lib/modules/%kernelrelease/build
fi

rm -rf %buildroot/lib/modules/%kernelrelease/build/Documentation
cp .config %buildroot/lib/modules/%kernelrelease/build

rm -f %buildroot/lib/modules/%kernelrelease/build/scripts/*.o
rm -f %buildroot/lib/modules/%kernelrelease/build/scripts/*/*.o

cp -a scripts/* %buildroot/lib/modules/%kernelrelease/build/scripts/
cp -a include/* %buildroot/lib/modules/%kernelrelease/build/include

# Make sure the Makefile and version.h have a matching timestamp so that
# external modules can be built
touch -r %buildroot/lib/modules/%kernelrelease/build/Makefile %buildroot/lib/modules/%kernelrelease/build/include/linux/version.h
touch -r %buildroot/lib/modules/%kernelrelease/build/.config %buildroot/lib/modules/%kernelrelease/build/include/linux/autoconf.h
# Copy .config to include/config/auto.conf so "make prepare" is unnecessary.
cp %buildroot/lib/modules/%kernelrelease/build/.config %buildroot/lib/modules/%kernelrelease/build/include/config/auto.conf

if test -s vmlinux.id; then
cp vmlinux.id %buildroot/lib/modules/%kernelrelease/build/vmlinux.id
else
echo >&2 "*** WARNING *** no vmlinux build ID! ***"
fi

#
# save the vmlinux file for kernel debugging into the kernel-debuginfo rpm
#
mkdir -p %buildroot%{debuginfodir}/lib/modules/%kernelrelease
cp vmlinux %buildroot%{debuginfodir}/lib/modules/%kernelrelease

find %buildroot/lib/modules/%kernelrelease -name "*.ko" -type f >modnames

# Move the devel headers out of the root file system
mkdir -p %buildroot/usr/src/kernels
mv %buildroot/lib/modules/%kernelrelease/build/* %buildroot/%src_install_dir
ln -sf $src_install_dir %buildroot/lib/modules/%kernelrelease/build


# Abort if there are any undefined symbols
msg="$(/sbin/depmod -F %buildroot/boot/System.map-%kernelrelease \
     -b %buildroot -ae %kernelrelease 2>&1)"

if [ $? -ne 0 ] || echo "$msg" | grep  'needs unknown symbol'; then
exit 1
fi

%post
/sbin/new-kernel-pkg --package %{name}-%{kernelrelease}\
        --mkinitrd --depmod --dracut\
        --kernel-args="max_loop=255"\
        --multiboot=/boot/xen.gz --banner="Qubes"\
        --make-default --install %{kernelrelease}

if [ -e /boot/grub/grub.conf ]; then
# Make it possible to enter GRUB menu if something goes wrong...
sed -i "s/^timeout *=.*/timeout=3/" /boot/grub/grub.conf 
fi

%posttrans
/sbin/new-kernel-pkg --package %{name}-%{kernelrelease} --rpmposttrans %{kernelrelease}

%preun
/sbin/new-kernel-pkg --rminitrd --rmmoddep --remove %{kernelrelease}

%files
%defattr(-, root, root)
%ghost /boot/initramfs-%{kernelrelease}.img
/boot/System.map-%{kernelrelease}
/boot/config-%{kernelrelease}
/boot/symvers-%kernelrelease.gz
%attr(0644, root, root) /boot/vmlinuz-%{kernelrelease}
/lib/firmware/%{kernelrelease}
/lib/modules/%{kernelrelease}

%package devel
Summary:        Development files necessary for building kernel modules
License:        GPL v2 only
Group:          Development/Sources
Provides:       multiversion(kernel)
Provides:       %name-devel = %version-%kernelrelease
AutoReqProv:    on

%description devel
This package contains files necessary for building kernel modules (and
kernel module packages) against the %build_flavor flavor of the kernel.

%post devel
if [ -f /etc/sysconfig/kernel ]
then
    . /etc/sysconfig/kernel || exit $?
fi
if [ "$HARDLINK" != "no" -a -x /usr/sbin/hardlink ]
then
    (cd /usr/src/kernels/%{kernelrelease} &&
     /usr/bin/find . -type f | while read f; do
       hardlink -c /usr/src/kernels/*.fc*.*/$f $f
     done)
fi


%files devel
%defattr(-,root,root)
/usr/src/kernels/%{kernelrelease}


%package domU
Summary:        The Xen Kernel
Version:        %{version}
Release:        %{rel}
License:        GPL v2 only
Group:          System/Kernel
Url:            http://www.kernel.org/
AutoReqProv:    on
BuildRequires:  coreutils module-init-tools sparse
Provides:       multiversion(kernel)
Provides:       %name = %version-%kernelrelease

Provides:       kernel-xen-domU
Provides:       kernel-qubes-domU
Provides:       kernel-drm-nouveau = 16

Requires(post): /sbin/new-kernel-pkg
Requires(preun):/sbin/new-kernel-pkg

Requires(pre):  coreutils gawk
Requires(post): dracut

Conflicts:      sysfsutils < 2.0
# root-lvm only works with newer udevs
Conflicts:      udev < 118
Conflicts:      lvm2 < 2.02.33
Provides:       kernel = %version-%kernelrelease

%description domU
Qubes domU kernel.

%post domU
/sbin/new-kernel-pkg --package %{name}-%{kernelrelease}\
        --mkinitrd --depmod --dracut\
        --banner="Qubes"\
        --make-default --install %{kernelrelease}

%posttrans domU
/sbin/new-kernel-pkg --package %{name}-%{kernelrelease} --rpmposttrans %{kernelrelease}

%preun domU
/sbin/new-kernel-pkg --rminitrd --rmmoddep --remove %{kernelrelease}

%files domU
%defattr(-, root, root)
%ghost /boot/initramfs-%{kernelrelease}.img
/boot/System.map-%{kernelrelease}
/boot/config-%{kernelrelease}
/boot/symvers-%kernelrelease.gz
%attr(0644, root, root) /boot/vmlinuz-%{kernelrelease}
/lib/firmware/%{kernelrelease}
/lib/modules/%{kernelrelease}


%changelog